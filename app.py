from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

@app.route('/create-triggers', methods=['POST'])
def create_triggers():
    data = request.get_json()

    SF_INSTANCE_URL = data['instance_url']
    SF_ACCESS_TOKEN = data['access_token']
    headers = {
        'Authorization': f'Bearer {SF_ACCESS_TOKEN}',
        'Content-Type': 'application/json'
    }

    query_url = f"{SF_INSTANCE_URL}/services/data/v60.0/query"
    soql_query = "SELECT Object_API_Name__c FROM ICP_Criteria_Cust__c GROUP BY Object_API_Name__c"
    response = requests.get(f"{query_url}?q={soql_query}", headers=headers)

    if response.status_code != 200:
        return jsonify({"error": "Failed to retrieve custom settings", "details": response.text}), 500

    results = response.json().get('records', [])
    object_api_names = [rec['Object_API_Name__c'] for rec in results]

    output = []

    for object_name in object_api_names:
        trigger_name = f"{object_name}ICPTrigger"
        check_query = f"SELECT Id FROM ApexTrigger WHERE TableEnumOrId = '{object_name}' AND Name = '{trigger_name}'"
        check_response = requests.get(f"{query_url}?q={check_query}", headers=headers)

        if check_response.status_code != 200:
            output.append({"object": object_name, "status": "error", "message": check_response.text})
            continue

        if check_response.json()['totalSize'] > 0:
            output.append({"object": object_name, "status": "exists", "message": "Trigger already exists"})
            continue

        trigger_body = f"""
trigger {trigger_name} on {object_name} (after insert, after update) {{
    if (TriggerRunOnceHelper.hasAlreadyRun('{trigger_name}')) return;
    TriggerRunOnceHelper.markRun('{trigger_name}');

    List<ICPScoreFlowHandlerGeneric.InputWrapper> inputList = new List<ICPScoreFlowHandlerGeneric.InputWrapper>();
    for ({object_name} record : Trigger.new) {{
        ICPScoreFlowHandlerGeneric.InputWrapper input = new ICPScoreFlowHandlerGeneric.InputWrapper();
        input.recordId = record.Id;
        input.objectApiName = '{object_name}';
        inputList.add(input);
    }}
    ICPScoreFlowHandlerGeneric.scoreGeneric(inputList);
}}
"""
        trigger_payload = {
            "Body": trigger_body,
            "Name": trigger_name,
            "TableEnumOrId": object_name,
            "UsageAfterInsert": True,
            "UsageAfterUpdate": True,
            "Status": "Active"
        }

        create_url = f'{SF_INSTANCE_URL}/services/data/v60.0/tooling/sobjects/ApexTrigger/'
        create_response = requests.post(create_url, headers=headers, json=trigger_payload)

        if create_response.status_code == 201:
            output.append({"object": object_name, "status": "created", "message": "Trigger created"})
        else:
            output.append({"object": object_name, "status": "failed", "message": create_response.text})

    return jsonify(output)
