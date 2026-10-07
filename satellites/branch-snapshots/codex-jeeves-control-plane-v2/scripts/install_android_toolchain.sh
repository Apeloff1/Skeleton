#!/usr/bin/env bash
# Idempotent installer for the cross-arch Android APK toolchain.
# Re-runs are safe — each step checks for prior completion.
set -e
LOG=/tmp/android_install.log
exec > >(tee -a "$LOG") 2>&1

echo "[$(date)] === Installing Android APK toolchain ==="

# 1. JDK + qemu + multiarch glibc
if ! command -v javac >/dev/null 2>&1 ; then
  echo "Installing openjdk-17 + qemu-user-static + libc6:amd64..."
  dpkg --add-architecture amd64 || true
  apt-get update -y -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
    openjdk-17-jdk-headless qemu-user-static libc6:amd64 unzip wget ca-certificates
else
  echo "JDK already installed: $(javac -version 2>&1)"
fi

export JAVA_HOME=$(dirname $(dirname $(readlink -f $(which javac 2>/dev/null || echo /usr/bin/javac))))
echo "JAVA_HOME=$JAVA_HOME"

# 2. Android cmdline-tools + build-tools + platforms
SDK=/opt/android-sdk
mkdir -p "$SDK/cmdline-tools"
if [ ! -d "$SDK/cmdline-tools/latest" ]; then
  echo "Downloading cmdline-tools..."
  cd /tmp
  wget -q https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip -O cmdline.zip
  unzip -q -o cmdline.zip -d "$SDK/cmdline-tools"
  mv "$SDK/cmdline-tools/cmdline-tools" "$SDK/cmdline-tools/latest"
  rm cmdline.zip
fi

SDKMANAGER="$SDK/cmdline-tools/latest/bin/sdkmanager"
yes | "$SDKMANAGER" --licenses --sdk_root="$SDK" >/dev/null 2>&1 || true

if [ ! -d "$SDK/build-tools" ] || [ -z "$(ls -A $SDK/build-tools 2>/dev/null)" ]; then
  echo "Installing build-tools + platforms..."
  "$SDKMANAGER" --sdk_root="$SDK" "build-tools;34.0.0" "platforms;android-34"
fi

# 3. Debug keystore
KEYDIR=/app/backend/data/build_artifacts/keys
mkdir -p "$KEYDIR"
KS=$KEYDIR/debug.keystore
if [ ! -f "$KS" ]; then
  echo "Creating debug keystore..."
  keytool -genkey -keyalg RSA -alias androiddebugkey -keypass android -keystore "$KS" \
    -storepass android -dname "CN=Android Debug,O=Android,C=US" -validity 10000 -keysize 2048
fi

echo "[$(date)] === DONE ==="
ls -la "$SDK/build-tools/" 2>&1
echo "qemu: $(which qemu-x86_64-static || echo MISSING)"
echo "apksigner: $(ls $SDK/build-tools/*/apksigner 2>&1 | head -1)"
