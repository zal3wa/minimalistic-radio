project('minimalistic-radio',
  version: '1.0.0',
  license: 'MIT',
  meson_version: '>= 1.0.0',
)

python = import('python').find_installation('python3')
i18n = import('i18n')

pkgdatadir = get_option('prefix') / get_option('datadir') / meson.project_name()
localedir = get_option('prefix') / get_option('localedir')

subdir('minimalistic_radio')

launcher_conf = configuration_data()
launcher_conf.set('PYTHON', python.full_path())
launcher_conf.set('pythondir', python.get_install_dir())
launcher_conf.set('localedir', localedir)
launcher_conf.set('pkgdatadir', pkgdatadir)
configure_file(
  input: 'bin/minimalistic-radio.in',
  output: 'minimalistic-radio',
  configuration: launcher_conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
)

subdir('data')
subdir('po')

# The HE-AAC check, run by CI inside the Flatpak and the Snap. Test-only, a few KB.
install_data('tools/check_aac.py', install_dir: pkgdatadir)
