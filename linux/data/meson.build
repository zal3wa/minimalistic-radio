app_id = 'io.github.zal3wa.MinimalisticRadio'

desktop_file = i18n.merge_file(
  input: app_id + '.desktop.in',
  output: app_id + '.desktop',
  type: 'desktop',
  po_dir: '../po',
  install: true,
  install_dir: get_option('datadir') / 'applications',
)

metainfo_file = i18n.merge_file(
  input: app_id + '.metainfo.xml.in',
  output: app_id + '.metainfo.xml',
  type: 'xml',
  po_dir: '../po',
  install: true,
  install_dir: get_option('datadir') / 'metainfo',
)

install_data(
  'icons/hicolor/scalable/apps' / app_id + '.svg',
  install_dir: get_option('datadir') / 'icons/hicolor/scalable/apps',
)
install_data(
  'icons/hicolor/symbolic/apps' / app_id + '-symbolic.svg',
  install_dir: get_option('datadir') / 'icons/hicolor/symbolic/apps',
)

desktop_validate = find_program('desktop-file-validate', required: false)
if desktop_validate.found()
  test('validate desktop file', desktop_validate, args: [desktop_file])
endif

appstreamcli = find_program('appstreamcli', required: false)
if appstreamcli.found()
  test('validate metainfo', appstreamcli, args: ['validate', '--no-net', metainfo_file])
endif
