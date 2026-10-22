#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
new_project.py: create a new Red Pitaya App from the dummy template.

The controls of the App (combo boxes, numbers, checkboxes, buttons and read-only monitors) are described
in an .ini file (see config.ini). Each control becomes a register of the dummy FPGA module
(fpga/rtl/dummy.v), a parameter of the C controller (src/) and an element of the web page (index.html),
already connected: the web page reads and writes the FPGA registers. The user then writes the logic in
dummy.v.

The App is created as a standalone project folder:

    <output>/<project>/              root Makefile, settings.sh, _settings.env, resources/, README, ...
    <output>/<project>/<App>/        the App (copy of dummy/, configured), with its app.ini

Steps:
  1. read and validate the .ini (nothing is written if it has errors)
  2. copy the template and the project files into a temporary folder
  3. set the App name (web page, info.json, fpga.conf, upload script), the optional Red Pitaya blocks
     (signal generator / PIDs) and the icons
  4. run <App>/config_tool.py -a, which writes the registers into dummy.v, the C code and the web page
  5. rename the temporary folder to the final one (on any error it is removed)

Requires Python >= 3.8 (standard library only). ImageMagick (mogrify) is optional, for the icon labels.
"""

import argparse
import configparser
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

TEMPLATE_ROOT = Path(__file__).resolve().parent         # rp_dummy2/
TEMPLATE_APP  = TEMPLATE_ROOT / 'dummy'                  # template of the App
PROJECT_FILES = TEMPLATE_ROOT / 'project_files'          # Makefile, gitignore, README, CHANGELOG

sys.dont_write_bytecode = True                          # no __pycache__ in the template folder
sys.path.insert(0, str(TEMPLATE_APP))
import config_lib                                        # noqa: E402  (ini parser/validator shared with config_tool.py)

# exit codes
EXIT_OK, EXIT_CONFIG, EXIT_USAGE, EXIT_FAIL = 0, 1, 2, 3

# build products and caches that may be in the template folder and must not be copied
TEMPLATE_IGNORE = shutil.ignore_patterns(
    '__pycache__', '*.pyc', '*.bak', '*.so', '*.o', 'obj', 'obj_dbg', 'obj_rld',
    'target', 'target_dbg', 'target_rld', '.Xil', '.srcs', 'out', 'sdk', 'project',
    'vivado*.log', 'vivado*.jou', '*.jou', 'usage_statistics_webtalk.*', 'red_pitaya.bit')

# fonts tried for the icon label (the first one installed is used)
ICON_FONTS = ('DejaVu-Sans-Bold', 'FreeSans-Bold', 'FreeSans-Negrita', 'Liberation-Sans-Bold', 'Helvetica-Bold')


class GenerationError(Exception):
    """Error while creating the App (the temporary folder is removed)"""


def say(msg):
    print(msg, flush=True)


# ------------------------------------------------------------------------------------------------
# Text edits

def edit_file(path, edits, count=None):
    """Apply regex edits [(pattern, replacement), ...] to a text file.

    count: if given, dict pattern -> number of matches required (GenerationError otherwise).
    """
    text = path.read_text(encoding='utf-8')
    for pat, rep in edits:
        text, n = re.subn(pat, rep, text, flags=re.M)
        if count and pat in count and n != count[pat]:
            raise GenerationError(f'{path.name}: expected {count[pat]} match(es) of {pat!r}, found {n}')
    path.write_text(text, encoding='utf-8')


def fill_template(src, dst, values):
    """Copy a text file replacing @KEY@ by values[KEY]"""
    text = src.read_text(encoding='utf-8')
    for k, v in values.items():
        text = text.replace(f'@{k}@', v)
    dst.write_text(text, encoding='utf-8')


def write_app_ini(src_ini, dst_ini, app_name):
    """Copy the .ini (with its comments) as app.ini, with [general] AppName = app_name"""
    text = Path(src_ini).read_text(encoding='utf-8')
    m = re.search(r'^\[general\][^\n]*\n', text, flags=re.M)
    if m is None:
        raise GenerationError('the .ini has no [general] section')
    sec_end = re.search(r'^\[', text[m.end():], flags=re.M)
    sec_end = m.end() + (sec_end.start() if sec_end else len(text) - m.end())
    general = text[m.end():sec_end]
    general, n = re.subn(r'^(\s*AppName\s*=).*$', rf'\g<1> {app_name}', general, flags=re.M | re.I)
    if n == 0:
        general = f'\nAppName = {app_name}\n' + general
    dst_ini.write_text(text[:m.end()] + general + text[sec_end:], encoding='utf-8')


def write_settings(path, cfg):
    """_settings.env of the project (board address for make upload)"""
    path.write_text('\n'.join([
        '#',
        '# Settings for Makefile (make upload): address and ssh/scp options of the Red Pitaya',
        '#',
        '',
        f'RPIP={cfg.rp_host}',
        f'RPOPTS={cfg.ssh_opts}',
        f'RPSCP={cfg.scp_opts}',
        '', '']), encoding='utf-8')


# ------------------------------------------------------------------------------------------------
# Icons

def label_icons(app_dir, app_name):
    """Write the App name at the bottom of the icons (ImageMagick). Returns a message or None if OK."""
    mogrify = shutil.which('mogrify')
    if mogrify is None:
        return 'ImageMagick (mogrify) not found: icons without label'
    font = None
    try:
        fonts = subprocess.run(['convert', '-list', 'font'], capture_output=True, text=True, timeout=30).stdout
        for name in ICON_FONTS:
            if re.search(rf'Font:\s+{re.escape(name)}\s*$', fonts, flags=re.M):
                font = name
                break
    except (OSError, subprocess.SubprocessError):
        pass
    size = 20 if len(app_name) <= 8 else max(9, int(160 / len(app_name)))
    draw = f"gravity south ; fill black text 0,12 '{app_name}' ; fill white text 1,11 '{app_name}'"
    for icon in ('icon.png', 'icon_DEBUG.png', 'icon_RELOAD.png'):
        cmd = [mogrify] + (['-font', font] if font else []) + ['-pointsize', str(size), '-draw', draw,
                                                               str(app_dir / 'info' / icon)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            return f'mogrify failed ({r.stderr.strip()[:200]}): icons without label'
    return None


# ------------------------------------------------------------------------------------------------
# Register map (for --dry-run)

def print_register_map(cfg):
    """Addresses of the registers of the controls (same rule as config_tool.py)"""
    base = 0x40600000
    if cfg.register_map == 'fixed':
        first = 4 * config_lib.USER_REGS_INDEX
        say('Register map (fixed): template registers at 0x000-0x0FC (read_ctrl 0x050), controls from 0x100')
    else:
        first = 0x050   # after the 20 template registers 0x000-0x04C; read_ctrl goes after the controls
        say('Register map (legacy): controls after the template registers, read_ctrl after the controls')
    say(f'  {"address":<12s} {"offset":<7s} {"register":<16s} {"type":<9s} {"bits":>4s}  {"range":<26s} label')
    for i, c in enumerate(cfg.controls):
        off = first + 4 * i
        rng = f'{c.min} .. {c.max}'
        say(f'  0x{base + off:08X}   0x{off:03X}   {c.name:<16s} {c.type:<9s} {c.nbits:4d}  {rng:<26s} {c.label}')
    if cfg.register_map == 'legacy':
        say(f'  0x{base + first + 4*len(cfg.controls):08X}   0x{first + 4*len(cfg.controls):03X}   read_ctrl')


# ------------------------------------------------------------------------------------------------
# Generation

def generate(cfg, ini_path, project_dir, args):
    """Create the project in a temporary folder and move it to project_dir"""
    app = cfg.app_name
    tmp_dir = project_dir.parent / f'.{project_dir.name}.tmp'
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    app_dir = tmp_dir / app
    try:
        say(f'[1/6] Copying the template {TEMPLATE_APP} -> {app}/')
        tmp_dir.mkdir(parents=True)
        shutil.copytree(TEMPLATE_APP, app_dir, ignore=TEMPLATE_IGNORE, symlinks=True)

        say('[2/6] Project files: Makefile, settings.sh, _settings.env, resources/, README.md, CHANGELOG.md, '
            'LICENSE, .gitignore')
        values = {'APP': app, 'DATE': datetime.now().strftime('%Y-%m-%d')}
        fill_template(PROJECT_FILES / 'Makefile',     tmp_dir / 'Makefile',     values)
        fill_template(PROJECT_FILES / 'README.md',    tmp_dir / 'README.md',    values)
        fill_template(PROJECT_FILES / 'CHANGELOG.md', tmp_dir / 'CHANGELOG.md', values)
        fill_template(PROJECT_FILES / 'gitignore',    tmp_dir / '.gitignore',   values)
        shutil.copy2(TEMPLATE_ROOT / 'settings.sh', tmp_dir / 'settings.sh')
        shutil.copy2(TEMPLATE_ROOT / 'LICENSE',     tmp_dir / 'LICENSE')
        shutil.copytree(TEMPLATE_ROOT / 'resources', tmp_dir / 'resources',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        write_settings(tmp_dir / '_settings.env', cfg)

        say(f'[3/6] App name "{app}": app.ini, index.html, info.json, fpga.conf, upload_app.sh')
        write_app_ini(ini_path, app_dir / 'app.ini', app)
        js_app = app.replace('\\', '\\\\').replace("'", "\\'")
        storage_key = re.sub(r'[^A-Za-z0-9_]', '_', app) + 'config'
        edits = [
            (r"var app_id = 'dummy';", f"var app_id = '{js_app}';"),
            (r'localStorage\.lockConfig', f'localStorage.{storage_key}'),
            (r'<h2 class="page-title">Oscilloscope\+Dummy</h2>', f'<h2 class="page-title">{app.replace("_", " ")}</h2>'),
        ]
        if not cfg.include_genfun:
            edits += [(r'<!-- DISABLE SignalGenerator -->', '<!-- DISABLE SignalGenerator'),
                      (r'// Events binding for signal generator', '/* DISABLE Events binding for signal generator')]
        if not cfg.include_pids:
            edits += [(r'<!-- DISABLE PIDController -->', '<!-- DISABLE PIDController'),
                      (r'// Events binding for PID Controller', '/* DISABLE Events binding for PID Controller')]
        edit_file(app_dir / 'index.html', edits, count={edits[0][0]: 1})
        (app_dir / 'fpga.conf').write_text(f'/opt/redpitaya/www/apps/{app}/red_pitaya.bit\n', encoding='utf-8')
        (app_dir / 'info' / 'info.json').write_text('\n'.join([
            '{',
            f'    "name": "{app}",',
            '    "version": "0.1.0-BUILD_NUMBER",',
            '    "revision": "REVISION",',
            '    "description": "Red Pitaya App generated with rp_dummy2 (dummy template: oscilloscope + custom FPGA module)."',
            '}']), encoding='utf-8')
        edit_file(app_dir / 'upload_app.sh', [(r'^APP="dummy"', f'APP="{app}"')], count={r'^APP="dummy"': 1})

        say(f'[4/6] FPGA blocks of Red Pitaya: signal generator {"included" if cfg.include_genfun else "removed (bus stub)"}, '
            f'PIDs {"included" if cfg.include_pids else "removed (bus stub)"}')
        edits = []
        if not cfg.include_genfun:
            edits.append((r'^(`define\s+INCLUDE_GENFUN\b.*)$', r'// \1 (disabled: include_genfun = False)'))
        if not cfg.include_pids:
            edits.append((r'^(`define\s+INCLUDE_PIDS\b.*)$', r'// \1 (disabled: include_pids = False)'))
        edit_file(app_dir / 'fpga' / 'rtl' / 'red_pitaya_top.v', edits, count={p: 1 for p, _ in edits})

        if args.no_icon:
            say('[5/6] Icons: not labeled (--no-icon)')
        else:
            say('[5/6] Icons: App name on icon.png, icon_DEBUG.png, icon_RELOAD.png')
            msg = label_icons(app_dir, app)
            if msg:
                say(f'      WARNING: {msg}')

        say(f'[6/6] Registers -> dummy.v, C controller, web page, py/hugo.py, tcl: {app}/config_tool.py -a')
        r = subprocess.run([sys.executable, '-B', str(app_dir / 'config_tool.py'), '-a'],
                           cwd=app_dir, capture_output=True, text=True)
        if args.verbose or r.returncode != 0:
            print(r.stdout, end='')
            print(r.stderr, end='', file=sys.stderr)
        if r.returncode != 0:
            raise GenerationError(f'config_tool.py -a failed (exit {r.returncode})')
        for cache in tmp_dir.rglob('__pycache__'):
            shutil.rmtree(cache, ignore_errors=True)

        if project_dir.exists():          # only with --force (checked before)
            shutil.rmtree(project_dir)
        tmp_dir.rename(project_dir)
    except BaseException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def looks_like_project(path):
    """True if path is empty or was made by this script (so --force may replace it)"""
    if not any(path.iterdir()):
        return True
    return any((d / 'app.ini').is_file() and (d / 'config_tool.py').is_file() for d in path.iterdir() if d.is_dir())


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='new_project.py',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description='Create a Red Pitaya App from the dummy template. Every control of the .ini becomes a\n'
                    'register of the FPGA module (fpga/rtl/dummy.v), a parameter of the C controller and an\n'
                    'element of the web page, already connected to each other. The App is created as a\n'
                    'standalone project folder: OUTPUT/PROJECT/ (Makefile, settings.sh, resources/...)\n'
                    'with the App in OUTPUT/PROJECT/NAME/.',
        epilog='control types in the .ini (one section per control, section name = register name):\n'
               '  combo     select box, bits_number 1..8 (optional: options = a, b, c)\n'
               '  number    integer input, bits_number 1..32, signed True/False\n'
               '  checkbox  1 bit\n'
               '  button    1 bit, toggles\n'
               '  monitor   read only value shown with a bar, bits_number 1..32, signed True/False\n'
               'optional keys: label, default (reset value).  See config.ini for an example.\n\n'
               'examples:\n'
               '  ./new_project.py -n -c my.ini my_app          check my.ini and show the register map\n'
               '  ./new_project.py -c my.ini -o ~/rp my_app     create ~/rp/rp_my_app/my_app/\n'
               '  ./new_project.py -u -o ~/rp my_app            rewrite ~/rp/rp_my_app/_settings.env\n\n'
               'exit status: 0 ok, 1 error in the .ini, 2 bad arguments, 3 generation failed')
    parser.add_argument('name', nargs='?', metavar='NAME',
                        help='App name (folder and URL of the App). Default: [general] AppName of the .ini. '
                             'Letters, digits, "_", "+" and "-", starting with a letter')
    parser.add_argument('-c', '--config', metavar='INI', default='config.ini',
                        help='file with the controls of the App (default: config.ini in the current folder, '
                             'or the one next to this script)')
    parser.add_argument('-o', '--output', metavar='DIR', default='.',
                        help='folder where the project folder is created (default: current folder)')
    parser.add_argument('-p', '--project', metavar='PROJECT',
                        help='name of the project folder (default: rp_NAME)')
    parser.add_argument('-n', '--dry-run', action='store_true',
                        help='only check the .ini and print the register map; write nothing')
    parser.add_argument('-f', '--force', action='store_true',
                        help='replace the project folder if it exists (only if it was made by this script)')
    parser.add_argument('-u', '--settings-only', action='store_true',
                        help='only (re)write _settings.env of an existing project from [general] rp_host, '
                             'ssh_opts, scp_opts')
    parser.add_argument('--no-icon', action='store_true',
                        help='do not write the App name on the icons (no ImageMagick needed)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='also show the output of config_tool.py')
    args = parser.parse_args(argv)

    # .ini: as given, or next to this script if it is the default and not in the current folder
    ini = Path(args.config).expanduser()
    if not ini.is_file() and args.config == 'config.ini' and (TEMPLATE_ROOT / 'config.ini').is_file():
        ini = TEMPLATE_ROOT / 'config.ini'
    ini = ini.resolve()

    say(f'Reading {ini}')
    try:
        cfg = config_lib.load_app_ini(str(ini), app_name=args.name)
    except ValueError as e:
        print('ERROR in the configuration:\n  ' + str(e).replace('\n', '\n  '), file=sys.stderr)
        return EXIT_CONFIG
    for w in cfg.warnings:
        say(f'WARNING: {w}')

    app = cfg.app_name
    project = args.project if args.project else f'rp_{app}'
    if not config_lib.APP_NAME_RE.match(project):
        print(f'ERROR: project folder name "{project}": use letters, digits, "_", "+" or "-"', file=sys.stderr)
        return EXIT_USAGE
    out_dir = Path(args.output).expanduser().resolve()
    project_dir = out_dir / project

    n_ctrl = {t: sum(1 for c in cfg.controls if c.type == t) for t in config_lib.CONTROL_TYPES}
    say(f'App "{app}": {len(cfg.controls)} controls (' +
        ', '.join(f'{n} {t}' for t, n in n_ctrl.items() if n) + '); '
        f'signal generator: {"yes" if cfg.include_genfun else "no"}, PIDs: {"yes" if cfg.include_pids else "no"}')

    if args.dry_run:
        print_register_map(cfg)
        say(f'Dry run: nothing written (the project would be {project_dir})')
        return EXIT_OK

    if args.settings_only:
        if not project_dir.is_dir():
            print(f'ERROR: {project_dir} does not exist', file=sys.stderr)
            return EXIT_USAGE
        write_settings(project_dir / '_settings.env', cfg)
        say(f'Written {project_dir / "_settings.env"} (RPIP={cfg.rp_host})')
        return EXIT_OK

    if not out_dir.is_dir():
        print(f'ERROR: output folder {out_dir} does not exist', file=sys.stderr)
        return EXIT_USAGE
    if TEMPLATE_ROOT in project_dir.parents:
        say(f'WARNING: the project is created inside the template repository ({TEMPLATE_ROOT})')
    if project_dir.exists():
        if not args.force:
            print(f'ERROR: {project_dir} already exists (use -f to replace it)', file=sys.stderr)
            return EXIT_USAGE
        if not project_dir.is_dir() or not looks_like_project(project_dir):
            print(f'ERROR: {project_dir} exists and does not look like a project made by new_project.py: '
                  f'not replaced', file=sys.stderr)
            return EXIT_USAGE
        say(f'{project_dir} exists: it will be replaced (--force)')

    say(f'Creating {project_dir}')
    try:
        generate(cfg, ini, project_dir, args)
    except (GenerationError, OSError, subprocess.SubprocessError) as e:
        print(f'ERROR: {e}\nNothing was created.', file=sys.stderr)
        return EXIT_FAIL

    say('')
    say(f'Done: {project_dir}')
    say('Next steps:')
    say(f'  cd {project_dir}')
    say(f'  # write your logic in {app}/fpga/rtl/dummy.v (registers listed in its "ADDED REGS" block)')
    say(f'  # after editing {app}/app.ini or adding modules to {app}/fpga/rtl/dummy/: ./{app}/config_tool.py -a')
    say('  source settings.sh && LANG=C make')
    return EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
