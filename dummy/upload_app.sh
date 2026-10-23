#!/bin/bash
#
# Upload this App to a Red Pitaya (Ecosystem 2.0 or 0.9x/1.0) through ssh/scp.
#
#   ./upload_app.sh [-w] [-r] [-p port] rp-XXXXXX.local
#
#   -w   upload only the web interface (index.html, css, js)
#   -r   restart the web server of the board (redpitaya_nginx, Ecosystem 2.0) after the upload, if the
#        nginx.conf of the App is new or changed: nginx reads the nginx.conf of the Apps only when it starts
#        (it disables the browser cache of index.html). The restart stops the App that is running.
#   -p   ssh port (default 22)
#
# Close the App (or stop it) before uploading it: its folder on the board is replaced.
# ssh uses your usual configuration and keys. If the board does not accept your key, ssh asks for the root
# password; to avoid it, install your key once with:  ssh-copy-id root@rp-XXXXXX.local
#

APP="dummy"

port_number=22
webonly=false
restart_nginx=false

usage() {
    echo "${0} [-w] [-r] [-p port_number] rp-XXXXXX.local"
    echo "   -w : upload only the web interface (index.html, css, js)"
    echo "   -r : restart redpitaya_nginx (Ecosystem 2.0) if the nginx.conf of the App is new or changed"
    echo "   -p : ssh port (default 22)"
}

OPTIND=1
while getopts "wrp:h?" opt; do
    case "$opt" in
    p)  port_number=$OPTARG ;;
    w)  webonly=true ;;
    r)  restart_nginx=true ;;
    h|\?)
        usage
        exit 0
        ;;
    esac
done
shift $((OPTIND-1))
[ "${1:-}" = "--" ] && shift

L=0
if [[ $LANG = *"es_"* ]]; then
  L=1
fi

if [ $# -lt 1 ]; then
  txt=( "You must provide the Red Pitaya hostname or IP:\n  ./upload_app.sh rp-XXXXXX.local\n"
        "Debes especificar el nombre de host o la dirección IP de la Red Pitaya:\n  ./upload_app.sh rp-XXXXXX.local\n")
  echo -e "${txt[$L]}"
  usage
  exit 1
fi
RPIP="$1"

# exit when any command fails, telling which one
set -e
trap 'last_command=$current_command; current_command=$BASH_COMMAND' DEBUG
trap 'echo -e "\n  \"${last_command}\" failed with exit code $?.\n"' ERR

RPOPTS="-l root -p ${port_number}"
RPSCP="-P ${port_number}"
APP_DIR="/opt/redpitaya/www/apps/${APP}"

# Files of the package: run from the package folder (target/) or from inside the App folder
if [ -d "./${APP}" ]; then
  cd "${APP}"
fi
if [ ! -f index.html ] || [ ! -f controllerhf.so ]; then
  echo "ERROR: run it from the package folder (the one with ${APP}/) or from ${APP}/ itself"
  exit 1
fi

echo "App: ${APP}    Red Pitaya: ${RPIP}"

# Login without password? (BatchMode: never prompts). If not, ssh/scp will ask for the root password.
if ssh -o BatchMode=yes -o ConnectTimeout=10 ${RPOPTS} "${RPIP}" true 2>/dev/null; then
  echo "ssh: login with your key OK"
else
  txt=( "ssh: the board does not accept your key: you will be asked for the root password (several times).\n     To avoid it: ssh-copy-id -p ${port_number} root@${RPIP}"
        "ssh: la placa no acepta tu llave: se va a pedir la clave de root (varias veces).\n     Para evitarlo: ssh-copy-id -p ${port_number} root@${RPIP}" )
  echo -e "${txt[$L]}"
fi

# The file system is made writable with the rw script of the OS: /opt/redpitaya/sbin/rw in Ecosystem 2.0,
# /boot/sbin/rw in 0.9x/1.0 (it needs PATH_REDPITAYA exported).
RP_RW='export PATH_REDPITAYA=/opt/redpitaya ; if [ -x /opt/redpitaya/sbin/rw ] ; then /opt/redpitaya/sbin/rw ; else /boot/sbin/rw ; fi'

echo -e "\n---------------------\n"

if $webonly ; then

    ssh ${RPOPTS} "${RPIP}" "${RP_RW} ; rm -rf ${APP_DIR}/index.html ${APP_DIR}/js ${APP_DIR}/css"
    scp ${RPSCP} -r index.html css js "root@${RPIP}:${APP_DIR}/"

else

    # md5 of the nginx.conf already on the board (empty if there is none) and Ecosystem 2.0 or not
    OLD_NGINX=$(ssh ${RPOPTS} "${RPIP}" "md5sum ${APP_DIR}/nginx.conf 2>/dev/null | cut -d' ' -f1 ; true")
    ECO2=$(ssh ${RPOPTS} "${RPIP}" "if [ -x /opt/redpitaya/sbin/rw ] && command -v systemctl > /dev/null ; then echo 1 ; else echo 0 ; fi")

    ssh ${RPOPTS} "${RPIP}" "${RP_RW} ; rm -rf ${APP_DIR} ; mkdir -p ${APP_DIR}"
    # Ecosystem 2.0: fpga.sh + fpga.bit.bin (+ nginx.conf). 0.9x/1.0: fpga.conf + red_pitaya.bit.
    # The _RELOAD package has neither fpga.sh nor bitstreams (it keeps the FPGA loaded): only what exists is sent.
    FILES="controllerhf.so css js nginx.conf fpga.conf index.html info py"
    for f in fpga.sh fpga.bit.bin red_pitaya.bit c ; do
        if [ -e "$f" ]; then FILES="$FILES $f"; fi
    done
    scp ${RPSCP} -r ${FILES} "root@${RPIP}:${APP_DIR}/"
    if [ -e fpga.sh ]; then
        ssh ${RPOPTS} "${RPIP}" "chmod 755 ${APP_DIR}/fpga.sh"   # Ecosystem 2.0 runs it with system()
    fi

    NEW_NGINX=$(md5sum nginx.conf | cut -d' ' -f1)
    if [ "${ECO2}" = "1" ] && [ "${OLD_NGINX}" != "${NEW_NGINX}" ]; then
        if $restart_nginx ; then
            echo "nginx.conf of the App is new or changed: restarting redpitaya_nginx (the running App stops)"
            ssh ${RPOPTS} "${RPIP}" "systemctl restart redpitaya_nginx"
        else
            txt=( "\nNOTE: the nginx.conf of the App is new or changed. Ecosystem 2.0 reads it only when the web server starts:\n      run again with -r, or on the board: systemctl restart redpitaya_nginx  (it stops the running App).\n      Until then the browser may cache index.html (an old page after an upgrade)."
                  "\nNOTA: el nginx.conf de la App es nuevo o cambió. Ecosystem 2.0 lo lee sólo al arrancar el servidor web:\n      volvé a correrlo con -r, o en la placa: systemctl restart redpitaya_nginx  (detiene la App que esté corriendo).\n      Hasta entonces el navegador puede guardar index.html en caché (una página vieja después de actualizar)." )
            echo -e "${txt[$L]}"
        fi
    fi

fi

echo -e "\n---------------------\n"

txt=( "Upload finished. Open the application in your browser:"
      "La aplicación fue subida. Abrila en el navegador:")
echo -e "${txt[$L]}"
echo "http://${RPIP}/${APP}/"
echo
