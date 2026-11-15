# Publishing the Linux version

For the owner. You do not need to know Linux: everything below is done in a browser, in a terminal on Windows (Git Bash or PowerShell), or on GitHub. The order is: Snap Store account, Flathub, then the first beta.

What is automated: when you push a tag that starts with `linux-v`, GitHub Actions builds the Flatpak and the Snap, runs the tests, creates the GitHub release with both files, and (if the Snap secret is set) publishes the Snap to the Snap Store. Nothing here touches the Windows release: Linux releases are never marked "latest".

## 1. Snap Store (Ubuntu's App Center)

`snapcraft` runs on Linux only. If you have no Linux computer, use an Ubuntu virtual machine or a GitHub Codespace (a Linux terminal in your browser). It is only needed once, for the login.

1. Create a free Ubuntu One account: <https://login.ubuntu.com>.
2. On the Linux machine install snapcraft: `sudo snap install snapcraft --classic` ([guide](https://snapcraft.io/docs/installing-snapcraft)).
3. Log in: `snapcraft login` (it asks for the Ubuntu One e-mail and password).
4. Reserve the name: `snapcraft register minimalistic-radio` ([guide](https://snapcraft.io/docs/registering-your-app-name)). If the name is taken the command says so, and we pick another.
5. Create the key GitHub will use. It can publish only this snap and only to the beta and stable channels:

   ```
   snapcraft export-login --snaps minimalistic-radio --channels beta,stable -
   ```

   The last `-` prints the key on the screen. Copy the whole text. It is a password: do not paste it anywhere except step 6.
6. On GitHub: the repository, Settings, Secrets and variables, Actions, New repository secret. Name: `SNAPCRAFT_STORE_CREDENTIALS`. Value: the text from step 5. ([GitHub's guide](https://docs.github.com/actions/security-guides/using-secrets-in-github-actions).)

The key expires after a year; repeat steps 5 and 6 then. Without the secret, the release job still works and just skips the Snap Store.

The first upload of a new snap name can be reviewed, which can take a day or two. Pre-releases go to the `beta` channel (install with `snap install minimalistic-radio --beta`), full releases to `stable`. Fill in the store page (description, screenshots) in the [Snap Store dashboard](https://snapcraft.io/minimalistic-radio/listing) once the name is registered.

## 2. Flathub

Flathub is the main app store for Flatpak (GNOME Software, Discover). Read the [submission guide](https://docs.flathub.org/docs/for-app-authors/submission) first. In short:

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

   The Meson project is the `linux` folder of the repository, so add `subdir: linux` to the module. Get the commit id with `git rev-parse "linux-v1.0.0^{commit}"`. (Ask Claude to prepare this file.)
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

Optional rehearsal, which publishes nothing: GitHub, Actions, the "Linux" workflow, Run workflow, choose branch `main`, tag `linux-v1.0.0-beta.1`, tick `dry_run`. It does every check and prints what it would do.

Then the real thing:

```
git checkout main
git pull
git tag -a linux-v1.0.0-beta.1 -m "First Linux beta: please test it with docs/LINUX-TEST-CHECKLIST.md"
git push origin linux-v1.0.0-beta.1
```

The tag message becomes the text of the release, so write it as you want people to read it. Watch the run under Actions. When it finishes, the release appears under Releases, marked "pre-release", with `minimalistic-radio.flatpak` and the `.snap` attached. If the secret is set, the Snap is also in the Snap Store `beta` channel.

Send testers the release link and `docs/LINUX-TEST-CHECKLIST.md`. For the full release use `linux-v1.0.0`; the Snap then goes to `stable`.

If a tag was wrong, delete the release on GitHub (Releases, the release, Delete), then run `git push origin :refs/tags/linux-v1.0.0-beta.1` and `git tag -d linux-v1.0.0-beta.1`, and make a new one.
