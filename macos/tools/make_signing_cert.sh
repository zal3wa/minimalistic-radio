#!/bin/sh
# Makes the Mac app's self-signed code-signing identity, once (docs/MACOS-PUBLISHING.md).
# Run it in an empty folder OUTSIDE the repository, in Git Bash or any shell with OpenSSL:
#
#   sh macos/tools/make_signing_cert.sh <folder>
#
# It writes into <folder>:
#   signing.p12       the certificate and its private key (keep it secret: password manager)
#   password.txt      the .p12's password (same)
#   signing.p12.b64   the .p12 as base64, for the GitHub secret MACOS_SIGNING_CERTIFICATE
# Nothing secret is printed.
set -e
export MSYS_NO_PATHCONV=1   # Git Bash would turn "/CN=..." into a Windows path
folder=${1:?"usage: make_signing_cert.sh <empty folder outside the repository>"}
mkdir -p "$folder"
cd "$folder"
umask 077
name="Minimalistic Radio (self-signed)"
openssl rand -base64 24 | tr -d '\n' > password.txt
openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes -subj "/CN=$name" \
  -addext "keyUsage=critical,digitalSignature" -addext "extendedKeyUsage=critical,codeSigning" \
  -addext "basicConstraints=critical,CA:false" -keyout key.pem -out cert.pem
# 3DES and SHA-1 MAC: what macOS's `security import` reads (OpenSSL 3's default PKCS#12 encryption it may not).
openssl pkcs12 -export -inkey key.pem -in cert.pem -name "$name" -passout file:password.txt \
  -certpbe PBE-SHA1-3DES -keypbe PBE-SHA1-3DES -macalg sha1 -out signing.p12
openssl base64 -A -in signing.p12 > signing.p12.b64
rm -f key.pem
echo "Made: $folder/signing.p12, password.txt, signing.p12.b64 and cert.pem (the public certificate)."
