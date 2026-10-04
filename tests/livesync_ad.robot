*** Settings ***
Documentation     Sync accounts from an AD group, against a real Samba AD
...               domain provisioned in the test VM. Install scenario only:
...               the update scenario is covered by livesync.robot.
Library           SSHLibrary
Library           String
Suite Setup       Prepare the AD suite
Suite Teardown    Remove the AD suite modules

*** Variables ***
${IMAGE_URL}         ghcr.io/platypuschan/obsidian-livesync:latest
${SCENARIO}          install
${SAMBA_IMAGE}       ghcr.io/nethserver/samba:3.5.0
${REALM}             ad.livesync.test
${GROUP}             obsidian-users
${HOST}              livesync-ad.test
${samba_id}          ${EMPTY}
${module_id}         ${EMPTY}
${web_port}          ${EMPTY}

*** Keywords ***
Prepare the AD suite
    Skip If    r'${SCENARIO}' != 'install'    AD sync is tested in the install scenario only

Remove the AD suite modules
    IF    r'${module_id}' != ''
        Execute Command    remove-module --no-preserve ${module_id}
    END
    IF    r'${samba_id}' != ''
        Execute Command    remove-module --no-preserve ${samba_id}
    END

Run task
    [Arguments]    ${agent}    ${action}    ${payload}={}
    ${output}    ${rc} =    Execute Command    api-cli run ${agent}/${action} --data '${payload}'
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    ${action} failed: ${output}
    RETURN    ${output}

Get configuration
    ${output} =    Run task    module/${module_id}    get-configuration
    &{config} =    Evaluate    json.loads(r'''${output}''')    modules=json
    RETURN    ${config}

Get account
    [Arguments]    ${username}
    ${config} =    Get configuration
    ${account} =    Evaluate    next(filter(lambda item: item['username'] == $username, $config['accounts']), None)
    RETURN    ${account}

Sync accounts
    Run task    module/${module_id}    sync-accounts

CouchDB status
    [Arguments]    ${method}    ${path}    ${auth}    @{options}
    ${extra} =    Catenate    @{options}
    ${output}    ${rc} =    Execute Command    curl -sS --max-time 10 -o /dev/null -w '\%{http_code}' -X ${method} -u '${auth}' ${extra} 'http://127.0.0.1:${web_port}${path}'
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    curl failed: ${output}
    RETURN    ${output}

Admin auth
    ${admin} =    Execute Command    runagent -m ${module_id} sh -c '. ./couchdb.env && printf %s "$COUCHDB_USER:$COUCHDB_PASSWORD"'
    RETURN    ${admin}

*** Test Cases ***
Provision a Samba AD domain
    ${output}    ${rc} =    Execute Command    add-module ${SAMBA_IMAGE} 1
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    add-module samba failed: ${output}
    &{output} =    Evaluate    ast.literal_eval(r'''${output}''')    modules=ast
    Set Suite Variable    ${samba_id}    ${output.module_id}
    ${output} =    Run task    module/${samba_id}    get-defaults    {"provision":"new-domain"}
    ${address} =    Evaluate    json.loads(r'''${output}''')['ipaddress_list'][0]['ipaddress']    modules=json
    Run task    module/${samba_id}    configure-module
    ...    {"provision":"new-domain","realm":"${REALM}","nbdomain":"LSTEST","hostname":"dc1","ipaddress":"${address}","adminuser":"administrator","adminpass":"Nethesis,1234"}

Create AD users and the group
    Run task    module/${samba_id}    add-user    {"user":"anna","display_name":"Anna","password":"Nethesis,1234","locked":false,"groups":[]}
    Run task    module/${samba_id}    add-user    {"user":"bert.b","display_name":"Bert","password":"Nethesis,1234","locked":false,"groups":[]}
    # A locked (disabled) member must not get an account
    Run task    module/${samba_id}    add-user    {"user":"carl","display_name":"Carl","password":"Nethesis,1234","locked":true,"groups":[]}
    Run task    module/${samba_id}    add-group    {"group":"${GROUP}","users":["anna","bert.b","carl"]}

Install and configure the module with AD sync
    ${output}    ${rc} =    Execute Command    add-module ${IMAGE_URL} 1
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    add-module failed: ${output}
    &{output} =    Evaluate    ast.literal_eval(r'''${output}''')    modules=ast
    Set Suite Variable    ${module_id}    ${output.module_id}
    ${port} =    Execute Command    runagent -m ${module_id} printenv TCP_PORT
    Set Suite Variable    ${web_port}    ${port.strip()}
    Run task    module/${module_id}    configure-module
    ...    {"host":"${HOST}","http2https":false,"lets_encrypt":false,"ad_enabled":true,"ad_domain":"${REALM}","ad_group":"${GROUP}","ad_nested_groups":false}
    ${timer} =    Execute Command    runagent -m ${module_id} systemctl --user is-enabled livesync-ad-sync.timer
    Should Be Equal    ${timer}    enabled

An unknown group is rejected
    ${output}    ${rc} =    Execute Command    api-cli run module/${module_id}/configure-module --data '{"host":"${HOST}","http2https":false,"lets_encrypt":false,"ad_enabled":true,"ad_domain":"${REALM}","ad_group":"no-such-group","ad_nested_groups":false}'
    ...    return_rc=True
    Should Not Be Equal As Integers    ${rc}    0
    Should Contain    ${output}    ad_group_not_found
    ${config} =    Get configuration
    Should Be Equal    ${config.ad_group}    ${GROUP}

Group members get accounts with their own database
    ${config} =    Get configuration
    Should Be True    ${config.ad_enabled}
    Should Be True    ${config.ad_last_sync['ok']}    ${config.ad_last_sync}
    ${anna} =    Get account    anna
    Should Be Equal    ${anna['source']}    ad
    Should Be True    ${anna['enabled']}
    Should Be Equal    ${anna['database']}    notes-anna
    ${bert} =    Get account    bert.b
    Should Be Equal    ${bert['database']}    notes-bert_b
    ${carl} =    Get account    carl
    Should Be Equal    ${carl}    ${None}    a disabled AD user got an account
    # The manual default account is still there
    ${default} =    Get account    livesync
    Should Be Equal    ${default['source']}    manual
    ${status} =    CouchDB status    PUT    /notes-anna/note    anna:${anna['password']}    -H 'Content-Type: application/json'    -d '{"a":1}'
    Should Be Equal    ${status}    201
    ${status} =    CouchDB status    PUT    /notes-bert_b/note    bert.b:${bert['password']}    -H 'Content-Type: application/json'    -d '{"b":1}'
    Should Be Equal    ${status}    201
    ${status} =    CouchDB status    GET    /notes-bert_b    anna:${anna['password']}
    Should Be Equal    ${status}    403
    Set Suite Variable    ${bert_password}    ${bert['password']}

Group-managed accounts cannot be deleted by hand
    ${output}    ${rc} =    Execute Command    api-cli run module/${module_id}/remove-account --data '{"username":"anna","delete_database":true}'
    ...    return_rc=True
    Should Not Be Equal As Integers    ${rc}    0
    Should Contain    ${output}    account_managed_by_ad

Leaving the group locks the user out and keeps the database
    Run task    module/${samba_id}    alter-group    {"group":"${GROUP}","users":["anna"]}
    Sync accounts
    ${bert} =    Get account    bert.b
    Should Not Be True    ${bert['enabled']}
    Should Be Empty    ${bert['password']}
    ${status} =    CouchDB status    GET    /notes-bert_b    bert.b:${bert_password}
    Should Not Be Equal    ${status}    200
    ${admin} =    Admin auth
    ${status} =    CouchDB status    GET    /notes-bert_b/note    ${admin}
    Should Be Equal    ${status}    200

Reset a database
    ${anna} =    Get account    anna
    Run task    module/${module_id}    reset-database    {"username":"anna"}
    ${status} =    CouchDB status    GET    /notes-anna/note    anna:${anna['password']}
    Should Be Equal    ${status}    404
    ${status} =    CouchDB status    PUT    /notes-anna/note    anna:${anna['password']}    -H 'Content-Type: application/json'    -d '{"a":2}'
    Should Be Equal    ${status}    201

Rejoining gets the old database with a new password
    Run task    module/${samba_id}    alter-group    {"group":"${GROUP}","users":["anna","bert.b"]}
    Sync accounts
    ${bert} =    Get account    bert.b
    Should Be True    ${bert['enabled']}
    Should Not Be Equal    ${bert['password']}    ${bert_password}
    ${status} =    CouchDB status    GET    /notes-bert_b/note    bert.b:${bert['password']}
    Should Be Equal    ${status}    200

A locked account can be deleted with its database
    Run task    module/${samba_id}    alter-group    {"group":"${GROUP}","users":["anna"]}
    Sync accounts
    Run task    module/${module_id}    remove-account    {"username":"bert.b","delete_database":true}
    ${bert} =    Get account    bert.b
    Should Be Equal    ${bert}    ${None}
    ${admin} =    Admin auth
    ${status} =    CouchDB status    GET    /notes-bert_b    ${admin}
    Should Be Equal    ${status}    404

Turning AD sync off keeps the accounts working
    ${anna} =    Get account    anna
    Run task    module/${module_id}    configure-module    {"host":"${HOST}","http2https":false,"lets_encrypt":false,"ad_enabled":false}
    ${anna_after} =    Get account    anna
    Should Be Equal    ${anna_after['source']}    manual
    Should Be Equal    ${anna_after['password']}    ${anna['password']}
    ${timer} =    Execute Command    runagent -m ${module_id} systemctl --user is-enabled livesync-ad-sync.timer
    Should Not Be Equal    ${timer}    enabled
    ${status} =    CouchDB status    GET    /notes-anna    anna:${anna['password']}
    Should Be Equal    ${status}    200
