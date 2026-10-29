// ESP32 ke ULN2003: IN1=GPIO 5, IN2=GPIO 18, IN3=GPIO 19, IN4=GPIO 21.
// Lihat arah putaran dari ujung poros motor.
const int IN1 = 5;
const int IN2 = 18;
const int IN3 = 19;
const int IN4 = 21;

// Ubah ke true jika perintah CW berputar berlawanan arah jarum jam.
const bool BALIK_ARAH = true;

const int stepMotor[4][4] = {
  {1, 1, 0, 0},
  {0, 1, 1, 0},
  {0, 0, 1, 1},
  {1, 0, 0, 1}
};

int indexStep = 0;
int arah = 1;
int kecepatan = 100;
bool motorNyala = false;
unsigned long waktuSebelumnya = 0;
unsigned long waktuLogSebelumnya = 0;
unsigned long jumlahLangkah = 0;

void jalankanMotor(int index) {
  digitalWrite(IN1, stepMotor[index][0]);
  digitalWrite(IN2, stepMotor[index][1]);
  digitalWrite(IN3, stepMotor[index][2]);
  digitalWrite(IN4, stepMotor[index][3]);
}

void matikanMotor() {
  motorNyala = false;
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
  Serial.println("[MOTOR] Motor berhenti, kumparan dimatikan.");
}

void setup() {
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  Serial.begin(115200);
  Serial.setTimeout(50);
  matikanMotor();
  Serial.println("ESP32 - Uji motor 28BYJ-48");
  Serial.println("ULN2003: IN1=5, IN2=18, IN3=19, IN4=21");
  Serial.println("Perintah: ON, OFF, CW, CCW, SPEED 100");
}

void loop() {
  if (Serial.available() > 0) {
    String perintah = Serial.readStringUntil('\n');
    perintah.trim();
    perintah.toUpperCase();

    if (perintah == "ON") {
      motorNyala = true;
      waktuSebelumnya = micros();
      waktuLogSebelumnya = millis();
      Serial.println("[OK] Motor dinyalakan.");
    } else if (perintah == "OFF") {
      matikanMotor();
    } else if (perintah == "CW") {
      arah = 1;
      Serial.println("[OK] Arah diatur: CW.");
    } else if (perintah == "CCW") {
      arah = -1;
      Serial.println("[OK] Arah diatur: CCW.");
    } else if (perintah.startsWith("SPEED ")) {
      int nilai = perintah.substring(6).toInt();
      if (nilai >= 10 && nilai <= 500) {
        kecepatan = nilai;
        Serial.print("[OK] Kecepatan langkah/detik: ");
        Serial.println(kecepatan);
      } else {
        Serial.println("[ERROR] Kecepatan harus 10-500.");
      }
    } else if (perintah.length() > 0) {
      Serial.println("[ERROR] Gunakan ON, OFF, CW, CCW, SPEED 100.");
    }
  }

  if (motorNyala) {
    unsigned long sekarang = micros();
    unsigned long interval = 1000000UL / kecepatan;
    if ((unsigned long)(sekarang - waktuSebelumnya) >= interval) {
      waktuSebelumnya = sekarang;
      int arahFisik = BALIK_ARAH ? -arah : arah;
      indexStep = (indexStep + arahFisik + 4) % 4;
      jalankanMotor(indexStep);
      jumlahLangkah++;
    }

    if (millis() - waktuLogSebelumnya >= 1000) {
      waktuLogSebelumnya = millis();
      Serial.print("[STATUS] Arah: ");
      Serial.print(arah == 1 ? "CW" : "CCW");
      Serial.print(" | Kecepatan: ");
      Serial.print(kecepatan);
      Serial.print(" langkah/detik | Total langkah: ");
      Serial.println(jumlahLangkah);
    }
  }
}
