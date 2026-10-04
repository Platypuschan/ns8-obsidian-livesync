*** Settings ***
Library    SSHLibrary
Library    String

*** Variables ***
${IMAGE_URL}         ghcr.io/platypuschan/obsidian-livesync:latest
# The update scenario starts from the last published release of this module;
# test-module-update.sh looks it up in the registry.
${PREVIOUS_IMAGE_URL}    ${EMPTY}
${SCENARIO}          install
${HOST}              livesync.test
${DATABASE}          obsidiannotes
${module_id}         ${EMPTY}
${web_port}          ${EMPTY}
${sync_auth}         ${EMPTY}
${ADMIN_USER}        admin
${ADMIN_PASSWORD}    Nethesis,1234

*** Keywords ***
Login to cluster-admin
    New Page    https://${NODE_ADDR}/cluster-admin/
    Fill Text    text="Username"    ${ADMIN_USER}
    Click    button >> text="Continue"
    Fill Text    text="Password"    ${ADMIN_PASSWORD}
    Click    button >> text="Log in"
    Wait For Elements State    css=#main-content    visible    timeout=10s

Read allocated web port
    ${port} =    Execute Command    runagent -m ${module_id} printenv TCP_PORT
    ${port} =    Strip String    ${port}
    Should Match Regexp    ${port}    ^[0-9]+$
    Set Suite Variable    ${web_port}    ${port}

Read sync credentials
    ${output}    ${rc} =    Execute Command    api-cli run module/${module_id}/get-configuration
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    get-configuration failed: ${output}
    &{config} =    Evaluate    json.loads(r'''${output}''')    modules=json
    Should Be Equal    ${config.username}    livesync
    Should Not Be Empty    ${config.password}
    Should Be Equal    ${config.url}    https://${HOST}
    Should Be Equal    ${config.database}    ${DATABASE}
    Set Suite Variable    ${sync_auth}    ${config.username}:${config.password}

CouchDB is up
    ${output}    ${rc} =    Execute Command    curl -fsS --max-time 5 -u '${sync_auth}' http://127.0.0.1:${web_port}/${DATABASE}
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0
    Should Contain    ${output}    "db_name":"${DATABASE}"

Wait until CouchDB is up
    Wait Until Keyword Succeeds    120 seconds    2 seconds    CouchDB is up

Configure current module
    ${payload} =    Evaluate    json.dumps({"host": $HOST, "http2https": False, "lets_encrypt": False, "database": $DATABASE})    modules=json
    ${output}    ${rc} =    Execute Command    api-cli run module/${module_id}/configure-module --data '${payload}'
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    configure-module failed: ${output}

Route
    [Arguments]    ${method}    ${path}    @{options}
    ${extra} =    Catenate    @{options}
    ${output}    ${rc} =    Execute Command    curl -sS --max-time 10 --resolve ${HOST}:80:127.0.0.1 -o /dev/null -w '%{http_code}' -X ${method} ${extra} 'http://${HOST}${path}'
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    curl failed: ${output}
    RETURN    ${output}

*** Test Cases ***
Add module for ${SCENARIO} scenario
    IF    r'${SCENARIO}' == 'update'
        Set Local Variable    ${install_image}    ${PREVIOUS_IMAGE_URL}
    ELSE
        Set Local Variable    ${install_image}    ${IMAGE_URL}
    END
    ${output}    ${rc} =    Execute Command    add-module ${install_image} 1
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    add-module ${install_image} failed: ${output}
    &{output} =    Evaluate    ast.literal_eval(r'''${output}''')    modules=ast
    Set Suite Variable    ${module_id}    ${output.module_id}

Configure initial module
    Configure current module
    Read allocated web port
    Read sync credentials
    Wait until CouchDB is up
    IF    r'${SCENARIO}' == 'update'
        # Leave a note in the vault database that must survive the update.
        ${output}    ${rc} =    Execute Command    curl -fsS --max-time 10 -u '${sync_auth}' -X PUT -H 'Content-Type: application/json' -d '{"note":"before-update"}' http://127.0.0.1:${web_port}/${DATABASE}/ci-before-update
        ...    return_rc=True
        Should Be Equal As Integers    ${rc}    0    write before update failed: ${output}
    END

Update module from the previous release
    Skip If    r'${SCENARIO}' != 'update'    only the update scenario updates the module
    Log    Scenario ${SCENARIO} with ${IMAGE_URL}    console=${True}
    # Same request as the Software Center: no forced pull.
    ${output}    ${rc} =    Execute Command    api-cli run update-module --data '{"module_url":"${IMAGE_URL}","instances":["${module_id}"]}'
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    update-module ${IMAGE_URL} failed: ${output}
    ${journal} =    Execute Command    journalctl -q --no-pager SYSLOG_IDENTIFIER=agent@${module_id}
    Should Not Contain    ${journal}    has failed    an update-module.d step failed
    ${image} =    Execute Command    runagent -m ${module_id} printenv IMAGE_URL
    ${image} =    Strip String    ${image}
    Should Be Equal    ${image}    ${IMAGE_URL}

Check service after install or update
    Read allocated web port
    Read sync credentials
    Wait until CouchDB is up

Check data and credentials kept by the update
    Skip If    r'${SCENARIO}' != 'update'    only the update scenario has data from the previous release
    ${output}    ${rc} =    Execute Command    curl -fsS --max-time 10 -u '${sync_auth}' http://127.0.0.1:${web_port}/${DATABASE}/ci-before-update
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    note lost by the update: ${output}
    Should Contain    ${output}    "note":"before-update"

Reconfigure keeps credentials and data
    ${before} =    Set Variable    ${sync_auth}
    Configure current module
    Read sync credentials
    Should Be Equal    ${sync_auth}    ${before}
    Wait until CouchDB is up

Check private credential files
    ${modes} =    Execute Command    runagent -m ${module_id} stat -c '%a' couchdb.env sync.env
    Should Be Equal    ${modes}    600\n600
    ${environment} =    Execute Command    runagent -m ${module_id} cat environment
    Should Not Contain    ${environment}    PASSWORD

CouchDB requires authentication
    ${status} =    Route    GET    /
    Should Be Equal    ${status}    401
    ${status} =    Route    GET    /${DATABASE}
    Should Be Equal    ${status}    401

CouchDB has the LiveSync server settings
    ${admin} =    Execute Command    runagent -m ${module_id} sh -c '. ./couchdb.env && printf %s "$COUCHDB_USER:$COUCHDB_PASSWORD"'
    FOR    ${key}    ${value}    IN
    ...    chttpd/require_valid_user    "true"
    ...    chttpd_auth/require_valid_user    "true"
    ...    chttpd/max_http_request_size    "4294967296"
    ...    couchdb/max_document_size    "50000000"
    ...    cors/credentials    "true"
    ...    cors/origins    "app://obsidian.md,capacitor://localhost,http://localhost"
    ...    cluster/n    "1"
        ${output} =    Execute Command    curl -fsS --max-time 5 -u '${admin}' http://127.0.0.1:${web_port}/_node/_local/_config/${key}
        Should Be Equal    ${output}    ${value}    ${key}
    END

CORS preflight from the Obsidian apps through Traefik
    FOR    ${origin}    IN    app://obsidian.md    capacitor://localhost    http://localhost
        ${headers} =    Execute Command    curl -sS --max-time 10 --resolve ${HOST}:80:127.0.0.1 -o /dev/null -D - -X OPTIONS -H 'Origin: ${origin}' -H 'Access-Control-Request-Method: PUT' -H 'Access-Control-Request-Headers: authorization,content-type' 'http://${HOST}/${DATABASE}'
        Should Match Regexp    ${headers}    (?im)^access-control-allow-origin: ${origin}\\r?$
        Should Match Regexp    ${headers}    (?im)^access-control-allow-credentials: true\\r?$
    END

LiveSync account works on its database through Traefik
    ${status} =    Route    PUT    /${DATABASE}/ci-${SCENARIO}    -u '${sync_auth}'    -H 'Content-Type: application/json'    -d '{"note":"via-traefik"}'
    Should Be Equal    ${status}    201
    # LiveSync stores design and local documents too.
    ${status} =    Route    PUT    /${DATABASE}/_design/ci-${SCENARIO}    -u '${sync_auth}'    -H 'Content-Type: application/json'    -d '{"views":{}}'
    Should Be Equal    ${status}    201
    ${status} =    Route    PUT    /${DATABASE}/_local/ci-${SCENARIO}    -u '${sync_auth}'    -H 'Content-Type: application/json'    -d '{"a":1}'
    Should Be Equal    ${status}    201

LiveSync account has no server rights
    ${status} =    Route    GET    /_node/_local/_config    -u '${sync_auth}'
    Should Be Equal    ${status}    401
    ${status} =    Route    PUT    /ci-forbidden-${SCENARIO}    -u '${sync_auth}'
    Should Be Equal    ${status}    401

Volumes and credentials are in the backup
    ${include} =    Execute Command    runagent -m ${module_id} sh -c 'cat ../etc/state-include.conf'
    FOR    ${line}    IN    state/couchdb.env    state/sync.env    volumes/couchdb-data    volumes/couchdb-etc
        Should Match Regexp    ${include}    (?m)^${line}$
    END
    ${rc} =    Execute Command    runagent -m ${module_id} podman volume exists couchdb-data
    ...    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    ${rc} =    Execute Command    runagent -m ${module_id} podman volume exists couchdb-etc
    ...    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0

Module UI loads in cluster-admin
    [Tags]    ui
    Import Library    Browser
    New Browser    chromium    headless=True
    New Context    ignoreHTTPSErrors=True
    Login to cluster-admin
    Go To    https://${NODE_ADDR}/cluster-admin/#/apps/${module_id}
    Wait For Elements State    iframe >>> h2 >> text="Status"    visible    timeout=20s
    Take Screenshot    filename=${OUTPUT DIR}/browser/screenshot/1._Status.png
    Go To    https://${NODE_ADDR}/cluster-admin/#/apps/${module_id}?page=settings
    Wait For Elements State    iframe >>> h2 >> text="Settings"    visible    timeout=20s
    # The heading renders even when module tasks fail; the fields are only
    # enabled and filled after get-configuration has completed
    Wait For Elements State    iframe >>> input[placeholder="livesync.example.org"]    enabled    timeout=30s
    Get Property    iframe >>> input[placeholder="livesync.example.org"]    value    ==    ${HOST}
    Get Property    iframe >>> input[placeholder="obsidiannotes"]    value    ==    ${DATABASE}
    Get Property    iframe >>> input#livesync-username    value    ==    livesync
    Get Property    iframe >>> input#livesync-uri    value    ==    https://${HOST}
    Take Screenshot    filename=${OUTPUT DIR}/browser/screenshot/2._Settings.png
    Close Browser

Remove module
    ${rc} =    Execute Command    remove-module --no-preserve ${module_id}
    ...    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0
