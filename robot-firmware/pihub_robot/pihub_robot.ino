/*
  Pi Hub robot firmware - Freenove 4WD ESP32 car (FNK0053), Arduino C++.

  What it does
   1. Connects to YOUR Wi-Fi router (edit the three lines below).
   2. Serves a MOTOR TEST page on its own IP (http://<robot-ip>/) with buttons that move
      the wheels straight away - use this first to prove the motors work.
   3. Polls the Pi Hub (http://pihub.local:8080/api/robot/next) every 300 ms for commands
      (forward/backward/left/right/stop/wake) and reports status back.
   4. Safety: motors stop by themselves 600 ms after the last move command.

  Board package: "esp32 by Espressif" in Arduino IDE. Board: "ESP32 Dev Module".
  Libraries: none beyond what ships with the ESP32 package (WiFi, WebServer, HTTPClient, Wire).

  Pins: PCA9685 on I2C SDA=13, SCL=14. Your boot log found the chip at 0x5F, so that is the default.
*/
#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <ESPmDNS.h>

// ---------- EDIT THESE ----------
const char* WIFI_SSID = "YOUR_WIFI_NAME";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";
const char* HUB_URL   = "http://pihub.local:8080";  // or http://192.168.x.x:8080 if .local fails
const char* HUB_TOKEN = "";                          // same as robot_token in hub/config.json, or empty
// --------------------------------

#define I2C_SDA 13
#define I2C_SCL 14
#define PCA_ADDR 0x5F
#define SPEED 2500            // 0..4095
#define MOVE_TIMEOUT_MS 600

// PCA9685 channels used by the Freenove 4WD board for the four motors (two channels per motor).
// If a wheel spins the wrong way, swap its two numbers.
const uint8_t M_FL[2] = {0, 1};
const uint8_t M_BL[2] = {3, 2};
const uint8_t M_FR[2] = {6, 7};
const uint8_t M_BR[2] = {4, 5};

WebServer server(80);
unsigned long lastMoveMs = 0;
unsigned long lastPollMs = 0;
unsigned long lastStatusMs = 0;
String lastCmd = "stop";
bool pcaOk = false;

// ---------- PCA9685 ----------
bool pcaWrite(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(PCA_ADDR);
  Wire.write(reg);
  Wire.write(val);
  return Wire.endTransmission() == 0;
}

void pcaSetPwm(uint8_t ch, uint16_t value) {
  uint8_t base = 0x06 + 4 * ch;
  Wire.beginTransmission(PCA_ADDR);
  Wire.write(base);
  Wire.write(0);
  Wire.write(0);
  Wire.write(value & 0xFF);
  Wire.write(value >> 8);
  Wire.endTransmission();
}

bool pcaInit() {
  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(100000);
  if (!pcaWrite(0x00, 0x10)) return false;  // sleep
  pcaWrite(0xFE, 121);                      // ~50 Hz prescale
  pcaWrite(0x00, 0x20);                     // wake, auto-increment
  delay(5);
  return true;
}

void motor(const uint8_t ch[2], int speed) {  // speed -4095..4095
  if (!pcaOk) return;
  if (speed > 0) { pcaSetPwm(ch[0], 0);     pcaSetPwm(ch[1], speed); }
  else if (speed < 0) { pcaSetPwm(ch[0], -speed); pcaSetPwm(ch[1], 0); }
  else { pcaSetPwm(ch[0], 0); pcaSetPwm(ch[1], 0); }
}

void drive(int fl, int bl, int fr, int br) {
  motor(M_FL, fl); motor(M_BL, bl); motor(M_FR, fr); motor(M_BR, br);
}

void doCommand(const String& cmd) {
  lastCmd = cmd;
  if (cmd == "forward")       { drive(SPEED, SPEED, SPEED, SPEED); lastMoveMs = millis(); }
  else if (cmd == "backward") { drive(-SPEED, -SPEED, -SPEED, -SPEED); lastMoveMs = millis(); }
  else if (cmd == "left")     { drive(-SPEED, -SPEED, SPEED, SPEED); lastMoveMs = millis(); }
  else if (cmd == "right")    { drive(SPEED, SPEED, -SPEED, -SPEED); lastMoveMs = millis(); }
  else if (cmd == "stop")     { drive(0, 0, 0, 0); }
  else if (cmd == "wake") {   // little wiggle so you can see an alarm reached the robot
    drive(SPEED, SPEED, -SPEED, -SPEED); delay(250);
    drive(-SPEED, -SPEED, SPEED, SPEED); delay(250);
    drive(0, 0, 0, 0);
  }
}

// ---------- local motor test page ----------
const char PAGE[] PROGMEM = R"HTML(<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Robot test</title>
<style>body{font-family:sans-serif;background:#111;color:#eee;text-align:center}
button{width:30%;height:90px;font-size:28px;margin:4px;border:0;border-radius:14px;background:#2a7fff;color:#fff;touch-action:manipulation}
.s{background:#e04040}</style></head><body><h2>Motor test</h2>
<div><button data-c=forward>&#9650;</button></div>
<div><button data-c=left>&#9664;</button><button class=s data-c=stop>STOP</button><button data-c=right>&#9654;</button></div>
<div><button data-c=backward>&#9660;</button></div>
<p id=m>Hold a button to drive. Releasing stops.</p>
<script>
let t;const go=c=>fetch('/cmd?c='+c).catch(()=>{});
document.querySelectorAll('button').forEach(b=>{
 const c=b.dataset.c;
 const start=e=>{e.preventDefault();go(c);if(c!='stop'){clearInterval(t);t=setInterval(()=>go(c),250);}};
 const end=e=>{e.preventDefault();clearInterval(t);if(c!='stop')go('stop');};
 b.addEventListener('pointerdown',start);b.addEventListener('pointerup',end);b.addEventListener('pointerleave',end);b.addEventListener('pointercancel',end);
});
</script></body></html>)HTML";

void handleRoot() { server.send_P(200, "text/html", PAGE); }
void handleCmd()  { doCommand(server.arg("c")); server.send(200, "text/plain", "ok"); }

// ---------- talking to the Pi Hub ----------
void addToken(HTTPClient& http) { if (strlen(HUB_TOKEN)) http.addHeader("X-Token", HUB_TOKEN); }

String jsonField(const String& body, const char* key) {  // tiny parser for flat string values
  String k = String("\"") + key + "\"";
  int i = body.indexOf(k);
  if (i < 0) return "";
  i = body.indexOf(':', i);
  int a = body.indexOf('"', i);
  int b = body.indexOf('"', a + 1);
  return (a >= 0 && b > a) ? body.substring(a + 1, b) : "";
}

void pollHub() {
  HTTPClient http;
  http.setTimeout(1500);
  http.begin(String(HUB_URL) + "/api/robot/next");
  addToken(http);
  if (http.GET() == 200) {
    String cmd = jsonField(http.getString(), "cmd");
    if (cmd.length()) doCommand(cmd);
  }
  http.end();
}

void sendStatus() {
  HTTPClient http;
  http.setTimeout(1500);
  http.begin(String(HUB_URL) + "/api/robot/status");
  http.addHeader("Content-Type", "application/json");
  addToken(http);
  String body = String("{\"ip\":\"") + WiFi.localIP().toString() + "\",\"rssi\":" + WiFi.RSSI() +
                ",\"last_cmd\":\"" + lastCmd + "\",\"motors_ok\":" + (pcaOk ? "true" : "false") + "}";
  http.POST(body);
  http.end();
}

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting to Wi-Fi");
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 20000) { delay(300); Serial.print('.'); }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Robot IP: "); Serial.println(WiFi.localIP());
    MDNS.begin("pirobot");
  } else {
    Serial.println("Wi-Fi failed - check name/password. Retrying in loop.");
  }
}

void setup() {
  Serial.begin(115200);
  pcaOk = pcaInit();
  Serial.println(pcaOk ? "PCA9685 OK" : "PCA9685 NOT FOUND - check wiring/address (0x5F or 0x40)");
  drive(0, 0, 0, 0);
  connectWifi();
  server.on("/", handleRoot);
  server.on("/cmd", handleCmd);
  server.begin();
}

void loop() {
  server.handleClient();

  if (WiFi.status() != WL_CONNECTED) {
    drive(0, 0, 0, 0);
    static unsigned long lastTry = 0;
    if (millis() - lastTry > 10000) { lastTry = millis(); WiFi.reconnect(); }
    return;
  }

  // dead-man switch
  if (lastCmd != "stop" && millis() - lastMoveMs > MOVE_TIMEOUT_MS) { drive(0, 0, 0, 0); lastCmd = "stop"; }

  if (millis() - lastPollMs > 300)   { lastPollMs = millis();   pollHub(); }
  if (millis() - lastStatusMs > 5000) { lastStatusMs = millis(); sendStatus(); }
}
