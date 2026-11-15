# Publishing the Mac version

For the owner. Everything happens on GitHub: the Mac app is built and signed by GitHub Actions on a Mac there, so nothing here needs a Mac except testing.

## What a release does

When you push a tag that starts with `macos-v`, the "macOS" workflow:

1. builds the app for Apple Silicon and Intel and runs its tests;
2. checks that the tag's version matches `MARKETING_VERSION` in `macos/project.yml` (stops if not);
3. signs the app with the project's own certificate (below);
4. makes `Minimalistic-Radio.dmg` (for people) and `Minimalistic-Radio-macOS.zip` (for the app's self-update);
5. creates the GitHub release, never marked "latest" (that stays the Windows app, whose updater and download button depend on it), and a pre-release for a `-beta.N` tag;
6. puts the DMG on the fixed release `macos-download`, which the README's "Download for macOS" button points to. Betas go there until the first full release; after that only full releases do.

Installed copies of the radio find the new version by themselves (every 6 hours, or Settings → Updates → Check now), show the green arrow, and update with one click.

## Making a beta or a release

On `main` (or the branch being tested), with `MARKETING_VERSION` in `macos/project.yml` already right:

```
git tag -a macos-v1.0.0-beta.1 -m "What's new, as people should read it"
git push origin macos-v1.0.0-beta.1
```

The tag message becomes the release notes. For a full release use `macos-v1.0.0`.

If the run is red, open it under Actions and read the failed step. A failure before "Publish the release" published nothing: fix it, delete the tag (`git push origin :refs/tags/macos-v1.0.0-beta.1` and `git tag -d macos-v1.0.0-beta.1`) and tag again. If "Publish the release" itself failed, "Re-run failed jobs" is safe: it only replaces the two files.

## Why it is signed with a self-made certificate

Apple's own signature (Developer ID and notarization) needs the Apple Developer Program, 99 USD a year, which the owner decided against. So:

- Every release is signed with one certificate made for this project. macOS then knows each version is the same app: no new permission prompts after an update, and the app only accepts an update signed with the same certificate.
- macOS still doesn't know who made it, so the first time someone opens the radio they choose "Open Anyway" in System Settings → Privacy & Security (the README explains it). Updates don't ask again.

## The certificate

- Two GitHub secrets: `MACOS_SIGNING_CERTIFICATE` (the certificate and its private key, a base64 .p12) and `MACOS_SIGNING_PASSWORD` (its password).
- The owner keeps `signing.p12` and its password in a password manager. GitHub secrets can't be read back, so that copy is the only one.
- It was made with `macos/tools/make_signing_cert.sh` and is valid until 2036.

If it is lost (or leaked): make a new one with the script, put it into both secrets, and publish. The installed copies only accept updates signed with the old certificate, so the radio can't update itself to that version: each Mac user downloads the DMG once and drags the radio to Applications again. Their stations and settings stay.

## If Apple's signature is wanted later

With the Apple Developer Program: replace the signing step in `.github/workflows/macos.yml` with a Developer ID certificate, add notarization (`xcrun notarytool`) and stapling, and the "Open Anyway" step disappears for new downloads. The app's update check then needs one change: accept the Developer ID requirement as well as the old certificate for one version, so existing installations can move over.
