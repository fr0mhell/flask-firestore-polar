# Required Imports
import os
from flask import Flask, request, jsonify
from firebase_admin import credentials, firestore, initialize_app
from operator import itemgetter
from math import ceil
import settings

# Initialize Flask App
app = Flask(__name__)

# Initialize Firestore DB
cred = credentials.Certificate(settings.KEY)
default_app = initialize_app(cred)
db = firestore.client()

PREPARED_DATA_REF = db.document('prepare/data')


@app.route('/prepare', methods=['POST'])
def prepare():
    """Prepare parameters for further experiments."""
    try:
        params = {
            'code_types': request.json.get('code_types', settings.CodeTypes.ALL),
            'code_lengths': request.json.get('code_lengths', []),
            'snr_range': request.json['snr_range'],
            'required_messages': request.json['required_messages'],
            'nodes': request.json['nodes'],
        }
        prepared_data = prepare_experiment_data(**params)

        PREPARED_DATA_REF.set({'experiments': prepared_data})

        return jsonify({"success": True}), 201
    except Exception as e:
        return f"An Error Occured: {e}"


def prepare_experiment_data(snr_range, required_messages, nodes,
                            code_types=None,
                            code_lengths=None,
                            channel_type='simple-bpsk'):
    """Prepare parameters for further experiments based on performed ones.
    There are some already performed experiments, so we need to consider them
    when going to reach some number of experiments.
    """
    results = list()

    for code_type in code_types:
        codes_ref = db.collection(code_type)

        if code_lengths:
            codes_ref.where('N', 'in', code_lengths)

        codes = codes_ref.list_documents()

        for code in codes:
            experiments_ref = db.collection(f'{code_type}/{code.id}/channels/{channel_type}/experiments')

            for snr in snr_range:
                experiments = experiments_ref.where('snr_db', '==', snr).list_documents()
                messages = required_messages - sum([e.to_dict()['frames'] for e in experiments])
                if messages == 0:
                    continue

                result = code.to_dict().copy()
                result.pop('type')
                result['code_id'] = code.id
                result['code_type'] = code_type
                result['channel_type'] = channel_type
                result['messages'] = messages
                result['snr'] = snr
                results.append(result)

    results = sorted(results, key=itemgetter('messages'))
    step = ceil(len(results) / nodes)
    return [results[i * step: (i + 1) * step] for i in range(len(results))]


@app.route('/get-params', methods=['GET'])
def get_params():
    """Get parameters for an experiment.
    Also, the parameter removed from list to be considered as already used.
    """
    try:
        experiments = PREPARED_DATA_REF.get().to_dict()

        if len(experiments['experiments']) == 0:
            return jsonify([]), 200

        response = experiments['experiments'].pop(0)
        PREPARED_DATA_REF.set(experiments)

        return jsonify(response), 200
    except Exception as e:
        return f"An Error Occured: {e}"


@app.route('/save-result', methods=['POST'])
def save_result():
    """Save experiment result for particular code."""
    try:
        result = request.json()

        route_params = result.pop('route_params')
        code_type = route_params.get('code_type')
        code_id = route_params.get('code_id')
        channel_type = route_params.get('channel_type')

        experiments_ref = db.collection(f'{code_type}/{code_id}/channels/{channel_type}/experiments')
        experiments_ref.set(result)

        return jsonify({"success": True}), 201
    except Exception as e:
        return f"An Error Occured: {e}"


port = int(os.environ.get('PORT', 8080))
if __name__ == '__main__':
    app.run(threaded=True, host='0.0.0.0', port=port)
