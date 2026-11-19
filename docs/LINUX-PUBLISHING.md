# Publishing the Linux version

For the owner. You do not need to know Linux: everything below is done in a browser, in a terminal on Windows (Git Bash or PowerShell, plus Ubuntu in WSL once for the Snap Store login), or on GitHub. The order is: Snap Store account, Flathub, then the first beta.

What is automated: when you push a tag that starts with `linux-v`, GitHub Actions builds the Flatpak and the Snap, runs the tests, publishes the Flatpak to the radio's own signed Flatpak repository (section 4, where testers get their updates), creates the GitHub release with both files, and (if the Snap secret is set) publishes the Snap to the Snap Store. Nothing here touches the Windows release: Linux releases are never marked "latest".

## 1. Snap Store (Ubuntu's App Center)

`snapcraft` runs on Linux only. On Windows 11 (Home is fine) use WSL, which runs Ubuntu inside Windows. It is only needed once, for the login:

- Open PowerShell as administrator and run `wsl --install -d Ubuntu-24.04` (or install "Ubuntu 24.04 LTS" from the Microsoft Store). Restart Windows if it asks.
- Open "Ubuntu 24.04" from the Start menu and choose a user name and password. This window is the Linux terminal for the steps below.
- Ubuntu 24.04 on WSL starts with systemd, which `snap` needs. If `snap` says the system does not support it, run `printf '[boot]\nsystemd=true\n' | sudo tee /etc/wsl.conf`, then `wsl --shutdown` in PowerShell, and open Ubuntu again.

1. Create a free Ubuntu One account: <https://login.ubuntu.com>.
2. In the Ubuntu terminal install snapcraft: `sudo snap install snapcraft --classic` ([guide](https://snapcraft.io/docs/installing-snapcraft)).
3. Log in: `snapcraft login` (it asks for the Ubuntu One e-mail and password). The first login may ask you to accept the developer agreement: accept it.
4. Reserve the name: `snapcraft register minimalistic-radio` ([guide](https://snapcraft.io/docs/registering-your-app-name)), or in the browser at <https://snapcraft.io/register-snap>, signed in with the same account. If the name is taken it says so, and we pick another.
5. Create the key GitHub will use. It can publish only this snap and only to the beta and stable channels:

   ```
   snapcraft export-login --snaps minimalistic-radio --channels beta,stable -
   ```

   The last `-` prints the key on the screen. Copy the whole text. It is a password: do not paste it anywhere except step 6.
6. On GitHub: the repository, Settings, Secrets and variables, Actions, New repository secret. Name: `SNAPCRAFT_STORE_CREDENTIALS`. Value: the text from step 5. ([GitHub's guide](https://docs.github.com/actions/security-guides/using-secrets-in-github-actions).)

The key expires after a year; repeat steps 5 and 6 then. Without the secret, the release job still works and just skips the Snap Store.

The first upload of a new snap name can be reviewed, which can take a day or two. Pre-releases go to the `beta` channel (install with `snap install minimalistic-radio --beta`), full releases to `stable`. Fill in the store page (description, screenshots) in the [Snap Store dashboard](https://snapcraft.io/minimalistic-radio/listing) once the name is registered.

## 2. Flathub

Flathub is the main app store for Flatpak (GNOME Software, Discover). Read the [submission guide](https://docs.flathub.org/docs/for-app-authors/submission) first.

Flathub's [generative AI policy](https://docs.flathub.org/docs/for-app-authors/requirements) (checked 2026-11-19) applies to this app, whose code, translations and packaging were written with Claude:

- the submitter must disclose AI-generated code, documentation and packaging, and reviewers may reject a submission for the extent of it;
- the Flathub manifest must not contain AI-generated or AI-assisted content, so you write it yourself;
- AI tools must not open the pull request or write its description, commit messages or replies, so you do those yourself too.

Undisclosed AI-generated material can get a submission rejected, and repeated violations can get you banned. In short:

1. Wait until the `linux` branch is merged into `main`. The screenshots in the app's description are loaded from `main` on GitHub, so they only resolve after the merge. This is why CI allows the linter message `appstream-missing-screenshots` while the screenshots are not on main yet.
2. Make the first real release (section 3), so there is a tag to point to.
3. Fork <https://github.com/flathub/flathub> to your GitHub account, with "Copy the master branch only" turned off (you need the `new-pr` branch).
4. In your fork, create a branch from `new-pr`, for example `add-minimalistic-radio`.
5. Add one file: `io.github.zal3wa.minimalistic-radio.yml`. It is `linux/flatpak/io.github.zal3wa.minimalistic-radio.yml` with one change: the `type: dir` source becomes a `git` source:

   ```
   sources:
     - type: git
       url: https://github.com/zal3wa/minimalistic-radio.git
       tag: linux-v1.0.0
       commit: <the full commit id of that tag>
   ```

   The Meson project is the `linux` folder of the repository, so add `subdir: linux` to the module. Get the commit id with `git rev-parse "linux-v1.0.0^{commit}"`. Write this file yourself (see the AI policy above).
6. Open a pull request from your branch to the **`new-pr`** branch of `flathub/flathub` (not `master`). Title: `Add io.github.zal3wa.minimalistic-radio`.
7. A bot builds the app and writes the result in the pull request; a Flathub reviewer then asks questions or requests changes. Answer on the pull request and push fixes to your branch. This usually takes days to weeks.
8. When it is approved, Flathub creates the repository `flathub/io.github.zal3wa.minimalistic-radio` and invites you. Accept the invitation (it needs two-factor authentication on your GitHub account). The app is on Flathub within a few hours.

What the linter exceptions in our CI mean:

- `appstream-external-screenshot-url` and `appstream-screenshots-not-mirrored-in-ostree`: our own build keeps the GitHub screenshot addresses, so the `.flatpak` from a release can show them. Flathub's build mirrors the screenshots itself, so these two do not apply there.
- `appstream-missing-screenshots`: only while the pictures are not yet on `main`.

The checkmark ("verified") on Flathub is for the app ID `io.github.zal3wa...`, and is proven through your GitHub account in the developer page after the first publish ([verification guide](https://docs.flathub.org/docs/for-app-authors/verification)).

When a store is live, edit `README.md`: remove the `<!-- -->` around that store's badge, and shorten the sentence about the GitHub release.

## 3. The first beta release

Do this on the merged `main`, with the version already right: `VERSION` in `linux/minimalistic_radio/__init__.py` and the newest `<release>` in `linux/data/io.github.zal3wa.minimalistic-radio.metainfo.xml.in` must both say `1.0.0`. The release job stops with an error if they differ from the tag.

Optional rehearsal, which publishes nothing: GitHub, Actions, the "Linux" workflow, Run workflow, choose branch `main`, tag `linux-v1.0.0-beta.1`, tick `dry_run`. It does every check, signs the Flatpak repository without publishing it, and prints what it would do.

Then the real thing:

```
git checkout main
git pull
git tag -a linux-v1.0.0-beta.1 -m "First Linux beta: please test it with docs/LINUX-TEST-CHECKLIST.md"
git push origin linux-v1.0.0-beta.1
```

The tag message becomes the text of the release, so write it as you want people to read it. Watch the run under Actions. When it finishes, the new version is in the Flatpak repository (testers who installed it get it as an update), and the release appears under Releases, marked "pre-release", with `minimalistic-radio.flatpak` and the `.snap` attached. If the secret is set, the Snap is also in the Snap Store `beta` channel.

Send new testers the install link (<https://zal3wa.github.io/minimalistic-radio/>) and `docs/LINUX-TEST-CHECKLIST.md`. For the full release use `linux-v1.0.0`; the Snap then goes to `stable`. The Flatpak repository has one branch, `stable`, for betas and full releases alike.

### If the run is red

- **A check job is red and the release job did not run** (for example the AAC or HLS check, which play live stations, or a rare GStreamer crash in the player tests): open the run, click "Re-run failed jobs". That is safe. The release job waits for the checks and then runs normally.
- **The release job is red at "Publish to the Snap Store", and the message says the upload needs a manual review** (possible for the first upload of a new snap): do not re-run. The GitHub release is there already. Wait for the Snap Store's e-mail that the review passed, then open <https://snapcraft.io/minimalistic-radio/releases> and release the uploaded revision to `beta` (or to `stable` for a full release).
- **The release job is red for another reason** (a wrong or expired `SNAPCRAFT_STORE_CREDENTIALS` secret, a Snap Store outage, a network error): fix the secret if needed (section 1, steps 5 and 6), then click "Re-run failed jobs". The release step sees that the GitHub release exists, only replaces its two files, and the Snap Store step runs again.
- **The repo, deploy or verify job is red** (section 4): the release job waits for them, so there is no release yet. If `verify` is red, the new version is already published; it is usually a download from Flathub that failed. Click "Re-run failed jobs" in both cases. If `repo` says the signing key does not match, see section 4.

If a tag was wrong, delete the release on GitHub (Releases, the release, Delete), then run `git push origin :refs/tags/linux-v1.0.0-beta.1` and `git tag -d linux-v1.0.0-beta.1`, and make a new one.

## 4. The Flatpak repository (automatic updates)

Testers install the radio once, from <https://zal3wa.github.io/minimalistic-radio/minimalistic-radio.flatpakref>, and every later version reaches them as an update: in GNOME Software or Discover, with `flatpak update`, and as the green arrow in the radio. The repository is a signed Flatpak repository on GitHub Pages of this GitHub repository. There is nothing to pay and no server to run.

How it is published: for each `linux-v...` tag, the workflow signs the new build with the repository's GPG key, adds it to the repository on branch `stable` (the previous version stays, with a small download from it to the new one), deploys GitHub Pages, and then installs the radio from there on a clean Ubuntu to check it. The `.flatpak` in the GitHub release comes from the same signed repository and brings it along as its remote, so a bundle install gets updates too.

To publish `main` without a release (for example after a failed deploy): Actions, the "Linux" workflow, Run workflow, branch `main`, tick `publish_repo`. It signs, deploys and checks, and creates no GitHub release.

Put a release tag on a commit that hasn't been published this way. GitHub Pages ignores a second deployment of the same commit, so the tag's run would fail its check (this is what stopped `linux-v1.0.0-beta.3`). Any new commit, even a small README change, avoids it.

The key:

- Two GitHub secrets: `FLATPAK_GPG_PRIVATE_KEY` (the private key, ASCII-armoured, no passphrase) and `FLATPAK_GPG_KEY_ID` (`2722144004B0F37F`).
- The public key is `linux/flatpak/minimalistic-radio.gpg`. It is public by design: the workflow puts it into the `.flatpakref`, the `.flatpakrepo` and the release `.flatpak`, and stops if the secret is not the matching private key.
- The backup of the private key is in your password manager. GitHub secrets cannot be read back, so keep that copy.
- GitHub Pages: Settings, Pages, Source "GitHub Actions". The `github-pages` environment (Settings, Environments) allows deploys from `main` and from `linux-v*` tags.

If the key is lost (or leaked): make a new key (ask Claude), put it into both secrets, replace `linux/flatpak/minimalistic-radio.gpg`, and publish. Testers' computers trust only the old key, so they refuse versions signed with the new one. Each tester removes the radio and its remote, then installs it again from the link; the stations and settings stay:

```
flatpak uninstall io.github.zal3wa.minimalistic-radio
flatpak remote-delete minimalistic-radio
flatpak install https://zal3wa.github.io/minimalistic-radio/minimalistic-radio.flatpakref
```

(Someone who installed the release `.flatpak` instead has a remote with another name: `flatpak remotes` shows it.)

Moving to Flathub later:

1. Get the app on Flathub (section 2). Flathub builds it itself and signs it with its own key.
2. An installed Flatpak follows the remote it came from, so testers do not move by themselves. Publish one last version to this repository marked end of life, with a message such as "Minimalistic Radio is now on Flathub: install it from there". Flatpak and GNOME Software show that message. (Ask Claude to add this to the workflow: it is `flatpak build-commit-from --end-of-life="..."`.)
3. Testers uninstall the radio and install it from Flathub. Their stations and settings stay, because the app ID is the same.
4. Point the README to Flathub instead of the `.flatpakref`. Keep GitHub Pages up for a few months, then remove the repo, deploy and verify jobs from the workflow.
