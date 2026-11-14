python.install_sources(
  '__init__.py',
  'app.py',
  'controller.py',
  'glib_scheduler.py',
  'i18n.py',
  'main.py',
  subdir: 'minimalistic_radio',
)

python.install_sources(
  'audio/__init__.py',
  'audio/player.py',
  'audio/playlists.py',
  subdir: 'minimalistic_radio/audio',
)

python.install_sources(
  'core/__init__.py',
  'core/covers.py',
  'core/directory.py',
  'core/models.py',
  'core/net.py',
  'core/storage.py',
  'core/streams.py',
  'core/titles.py',
  subdir: 'minimalistic_radio/core',
)

python.install_sources(
  'platform/__init__.py',
  'platform/menu_model.py',
  subdir: 'minimalistic_radio/platform',
)

python.install_sources(
  'ui/__init__.py',
  'ui/footer.py',
  'ui/logos.py',
  'ui/reorder.py',
  'ui/stations_page.py',
  'ui/window.py',
  subdir: 'minimalistic_radio/ui',
)

# Loaded by ui/window.py from next to the module.
install_data('ui/style.css', install_dir: python.get_install_dir() / 'minimalistic_radio' / 'ui')
