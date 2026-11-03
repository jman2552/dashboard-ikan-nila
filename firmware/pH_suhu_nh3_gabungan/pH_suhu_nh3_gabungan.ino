/**
 * ============================================================================
 * PROGRAM GABUNGAN: MONITORING pH, SUHU (DS18B20), & AMONIA (MQ-137)
 * DENGAN INTEGRASI FIREBASE REALTIME DATABASE PADA ESP32
 * ============================================================================
 * 
 * Hardware:
 * - ESP32 Dev Module
 * - ADS1115 I2C ADC (SDA: GPIO 21, SCL: GPIO 22)
 *   - A0: Sensor pH DFRobot (Analog)
 *   - A1: Sensor Gas Amonia MQ-137 (Analog)
 * - Sensor Suhu DS18B20 Waterproof (Data: GPIO 4 dengan resistor pull-up 4.7k ke 3.3V)
 * 
 * Node Firebase yang diupdate:
 * - /device/current : Data pembacaan terkini (temp, ph, nh3, ts, firmware)
 * - /device/history : Riwayat data berkala untuk grafik dashboard
 * ============================================================================
 */

#include <WiFi.h>
#include <Wire.h>
#include <EEPROM.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <Adafruit_ADS1X15.h>
#include <FirebaseESP32.h>
#include <time.h>

// ─────────────────────────────────────────────────────────────
// 1. KONFIGURASI WIFI & FIREBASE
// ─────────────────────────────────────────────────────────────
#define WIFI_SSID       "Kos22 Lt1 Ext"
#define WIFI_PASSWORD   "13245678"

#define DATABASE_URL    "amonia-projet-ta-default-rtdb.asia-southeast1.firebasedatabase.app"
#define DATABASE_SECRET "uudDwzJi5llIT275Pky7OqSSF3jNY4hsk0jPIP2P"

// Interval pengiriman data ke Firebase (default: tiap 10 detik / 10000 ms)
#define FIREBASE_SEND_INTERVAL 10000 

FirebaseData fbdo;
FirebaseAuth auth;
FirebaseConfig config;

// ─────────────────────────────────────────────────────────────
// 2. KONFIGURASI ADS1115 (I2C: SDA=21, SCL=22)
// ─────────────────────────────────────────────────────────────
Adafruit_ADS1115 ads;

// ─────────────────────────────────────────────────────────────
// 3. KONFIGURASI SENSOR SUHU (DS18B20)
// ─────────────────────────────────────────────────────────────
#define ONE_WIRE_BUS 4 // Pin data DS18B20 di GPIO 4
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

const int SUHU_SAMPLES = 10;
const float KALIBRASI_SUHU = -0.64; // Nilai kalibrasi suhu Anda

// ─────────────────────────────────────────────────────────────
// 4. KONFIGURASI SENSOR pH (DFRobot via ADS1115 Pin A0)
// ─────────────────────────────────────────────────────────────
#define EEPROM_NEUTRAL_VOLTAGE_ADDRESS 0
#define EEPROM_ACID_VOLTAGE_ADDRESS 4

#define PH_ARRAY_LENGTH 30
int pHArray[PH_ARRAY_LENGTH];
int pHArrayIndex = 0;
bool pHArrayFull = false;

float phVoltage = 0.0;
float phValue   = 7.0;
float neutralVoltage = 1596.38; // Default kalibrasi pH 7 (mV)
float acidVoltage    = 2041.07; // Default kalibrasi pH 4 (mV)

// ─────────────────────────────────────────────────────────────
// 5. KONFIGURASI SENSOR AMONIA MQ-137 (via ADS1115 Pin A1)
// ─────────────────────────────────────────────────────────────
const float RL_VALUE = 10.0;  // 10 kOhm
const float R0_VALUE = 43.60; // Kalibrasi udara bersih
const float m_curve  = -0.243;
const float b_curve  = 0.323;

float nh3_ppm = 0.0;

// ─────────────────────────────────────────────────────────────
// 6. SINKRONISASI WAKTU NTP (WIB = UTC+7)
// ─────────────────────────────────────────────────────────────
#define NTP_SERVER "pool.ntp.org"
#define GMT_OFFSET 25200 // 7 * 3600
#define DST_OFFSET 0

unsigned long lastSendTime = 0;

// ─────────────────────────────────────────────────────────────
// FUNGSI FILTER RATA-RATA pH (MEMBUANG NILAI EKSTREM)
// ─────────────────────────────────────────────────────────────
double avergearray(int* arr, int number) {
  int i, max_val, min_val;
  long long amount = 0;
  if (number <= 0) return 0;
  if (number < 5) {
    for (i = 0; i < number; i++) amount += arr[i];
    return (double)amount / number;
  } else {
    min_val = arr[0];
    max_val = arr[0];
    for (i = 1; i < number; i++) {
      if (arr[i] < min_val) min_val = arr[i];
      if (arr[i] > max_val) max_val = arr[i];
      amount += arr[i];
    }
    amount = amount - min_val - max_val;
    return (double)amount / (number - 2);
  }
}

// ─────────────────────────────────────────────────────────────
// FUNGSI MEMBACA SENSOR SUHU DS18B20
// ─────────────────────────────────────────────────────────────
float bacaSuhu() {
  float total = 0;
  int count = 0;
  for (int i = 0; i < SUHU_SAMPLES; i++) {
    sensors.requestTemperatures();
    float s = sensors.getTempCByIndex(0);
    if (s != DEVICE_DISCONNECTED_C && s > -20.0 && s < 85.0) {
      total += s;
      count++;
    }
    delay(20);
  }
  if (count > 0) {
    return (total / count) + KALIBRASI_SUHU;
  }
  return 28.0; // Fallback jika sensor terlepas
}

// ─────────────────────────────────────────────────────────────
// FUNGSI MEMBACA SENSOR pH (ADS1115 A0)
// ─────────────────────────────────────────────────────────────
float bacaPH() {
  int16_t adc = ads.readADC_SingleEnded(0);
  pHArray[pHArrayIndex++] = adc;
  if (pHArrayIndex >= PH_ARRAY_LENGTH) {
    pHArrayIndex = 0;
    pHArrayFull = true;
  }

  int jumlah = pHArrayFull ? PH_ARRAY_LENGTH : pHArrayIndex;
  if (jumlah <= 0) jumlah = 1;

  float adcFiltered = avergearray(pHArray, jumlah);
  phVoltage = adcFiltered * 0.125; // dalam mV

  float slope = (7.0 - 4.0) / ((neutralVoltage - 1500.0) / 3.0 - (acidVoltage - 1500.0) / 3.0);
  float intercept = 7.0 - slope * (neutralVoltage - 1500.0) / 3.0;
  float calculatedPH = slope * (phVoltage - 1500.0) / 3.0 + intercept;

  if (calculatedPH < 0.0)  calculatedPH = 0.0;
  if (calculatedPH > 14.0) calculatedPH = 14.0;
  return calculatedPH;
}

// ─────────────────────────────────────────────────────────────
// FUNGSI MEMBACA SENSOR AMONIA MQ-137 (ADS1115 A1)
// ─────────────────────────────────────────────────────────────
float bacaNH3() {
  float totalAdc = 0;
  for (int i = 0; i < 50; i++) {
    totalAdc += ads.readADC_SingleEnded(1);
    delay(2);
  }
  float avgAdc = totalAdc / 50.0;
  float VRL = (avgAdc * 0.125) / 1000.0; // Volt

  if (VRL <= 0.01) return 0.0;

  float Rs = ((5.0 / VRL) - 1.0) * RL_VALUE;
  float ratio = Rs / R0_VALUE;

  if (ratio >= 3.40) {
    ratio = 3.65;
  }

  float ppm = pow(10, ((log10(ratio) - b_curve) / m_curve));
  if (ppm <= 0.15) {
    ppm = 0.0;
  }
  return ppm;
}

// ─────────────────────────────────────────────────────────────
// AMBIL WAKTU EPOCH MILLISECOND
// ─────────────────────────────────────────────────────────────
int64_t getEpochMs() {
  time_t nowSec;
  time(&nowSec);
  if (nowSec < 100000) return 0;
  return (int64_t)nowSec * 1000;
}

// ─────────────────────────────────────────────────────────────
// EVALUASI STATUS KONDISI AIR
// ─────────────────────────────────────────────────────────────
String tentukanStatus(float suhu, float ph, float nh3) {
  if (nh3 > 0.10) return "Bahaya Amonia Tinggi";
  if (ph < 6.5)   return "pH Asam";
  if (ph > 8.5)   return "pH Basa";
  if (suhu < 26.0) return "Suhu Dingin";
  if (suhu > 33.0) return "Suhu Panas";
  return "Ideal / Normal";
}

// ─────────────────────────────────────────────────────────────
// SETUP
// ─────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n╔════════════════════════════════════════════════╗");
  Serial.println("║   ESP32 — MONITORING pH, SUHU & AMONIA NH3     ║");
  Serial.println("║            KOLAM IKAN NILA                     ║");
  Serial.println("╚════════════════════════════════════════════════╝");

  Wire.begin(21, 22);
  if (!ads.begin()) {
    Serial.println("❌ Modul ADS1115 tidak ditemukan! Cek kabel SDA/SCL.");
  } else {
    ads.setGain(GAIN_ONE);
    Serial.println("✅ ADS1115 terdeteksi.");
  }

  sensors.begin();
  sensors.setResolution(12);
  Serial.println("✅ Sensor Suhu DS18B20 aktif.");

  EEPROM.begin(512);
  float e_neutral = EEPROM.readFloat(EEPROM_NEUTRAL_VOLTAGE_ADDRESS);
  float e_acid    = EEPROM.readFloat(EEPROM_ACID_VOLTAGE_ADDRESS);
  if (!isnan(e_neutral) && e_neutral > 500 && e_neutral < 3000) neutralVoltage = e_neutral;
  if (!isnan(e_acid) && e_acid > 500 && e_acid < 3000) acidVoltage = e_acid;
  Serial.printf("   Kalibrasi pH: Neutral=%.2f mV | Acid=%.2f mV\n", neutralVoltage, acidVoltage);

  Serial.printf("\n🌐 Menghubungkan ke WiFi '%s'...", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int retryWiFi = 0;
  while (WiFi.status() != WL_CONNECTED && retryWiFi < 25) {
    delay(500);
    Serial.print(".");
    retryWiFi++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✅ WiFi Terhubung!");
    Serial.printf("   IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n⚠️ WiFi belum terhubung, mencoba jalan mandiri...");
  }

  configTime(GMT_OFFSET, DST_OFFSET, NTP_SERVER);
  Serial.println("⏰ Sinkronisasi NTP waktu...");

  Serial.println("🔥 Menghubungkan ke Firebase Realtime Database...");
  config.host = DATABASE_URL;
  config.signer.tokens.legacy_token = DATABASE_SECRET;
  Firebase.begin(&config, &auth);
  Firebase.reconnectWiFi(true);
  Serial.println("✅ Firebase Client Siap.");
}

// ─────────────────────────────────────────────────────────────
// LOOP UTAMA
// ─────────────────────────────────────────────────────────────
void loop() {
  float suhuSekarang = bacaSuhu();
  float phSekarang   = bacaPH();
  float nh3Sekarang  = bacaNH3();
  String statusAir   = tentukanStatus(suhuSekarang, phSekarang, nh3Sekarang);

  static unsigned long lastPrint = 0;
  if (millis() - lastPrint >= 2000) {
    lastPrint = millis();
    Serial.printf("[SENSOR] Suhu: %.2f °C | pH: %.2f | NH3: %.3f ppm | Status: %s\n",
                  suhuSekarang, phSekarang, nh3Sekarang, statusAir.c_str());
  }

  if (millis() - lastSendTime >= FIREBASE_SEND_INTERVAL) {
    lastSendTime = millis();

    if (WiFi.status() == WL_CONNECTED) {
      int64_t tsMs = getEpochMs();
      if (tsMs == 0) {
        tsMs = (int64_t)millis();
      }

      // 1. Update /device/current
      FirebaseJson jsonCurrent;
      jsonCurrent.set("temp", suhuSekarang);
      jsonCurrent.set("ph", phSekarang);
      jsonCurrent.set("nh3", nh3Sekarang);
      jsonCurrent.set("status", statusAir);
      jsonCurrent.set("firmware", "2.1.0");
      jsonCurrent.set("ts", String((unsigned long)(tsMs / 1000)));

      if (Firebase.updateNode(fbdo, "/device/current", jsonCurrent)) {
        Serial.println("   🚀 Firebase: /device/current terupdate!");
      } else {
        Serial.printf("   ⚠️ Gagal update current: %s\n", fbdo.errorReason().c_str());
      }

      // 2. Simpan Riwayat ke /device/history
      FirebaseJson jsonHistory;
      jsonHistory.set("temp", suhuSekarang);
      jsonHistory.set("ph", phSekarang);
      jsonHistory.set("nh3", nh3Sekarang);
      jsonHistory.set("status", statusAir);
      jsonHistory.set("firmware", "2.1.0");
      jsonHistory.set("ts", String((unsigned long)(tsMs / 1000)));

      if (Firebase.pushJSON(fbdo, "/device/history", jsonHistory)) {
        Serial.println("   💾 Firebase: Riwayat baru tersimpan di /device/history");
      } else {
        Serial.printf("   ⚠️ Gagal push history: %s\n", fbdo.errorReason().c_str());
      }
    } else {
      Serial.println("   ⚠️ WiFi terputus, mencoba rekoneksi...");
      WiFi.reconnect();
    }
  }

  delay(50);
}
