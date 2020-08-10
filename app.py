import os
from math import ceil
from uuid import uuid4

from firebase_admin import credentials, firestore, initialize_app
from flask import Flask, jsonify, request

import config

# Initialize Flask App
app = Flask(__name__)
default_app = initialize_app()

if config.ENVIRONMENT != 'production':
    from key import KEY
    # Initialize Firestore DB with local credentials
    cred = credentials.Certificate(KEY)

db = firestore.client()
PREPARED_COL_REF = db.collection(config.PREPARED_COL_ID)


@app.route('/prepare', methods=['POST'])
def prepare():
    """Prepare parameters for further experiments."""
    try:
        params = request.json
        prepared_data = prepare_experiment_data(**params)

        for i in range(0, len(prepared_data), config.BATCH_SIZE):
            batch = db.batch()
            for data in prepared_data[i: i+config.BATCH_SIZE]:
                batch.set(PREPARED_COL_REF.document(str(uuid4())), data)
            batch.commit()

        return jsonify({'experiments': len(prepared_data)}), 201
    except Exception as e:
        return f'An Error Occurred: {e}\nRequest: {request.json}', 400


def prepare_experiment_data(
        snr_range: list,
        required_messages: int,
        codes: dict,
        per_experiment=1000,
        channel_type='simple-bpsk', **kwargs,
):
    """Prepare parameters for further experiments based on performed ones.
    There are some already performed experiments, so we need to consider them
    when going to reach some number of experiments.
    """
    results = list()

    for code_type, code_ids in codes.items():

        for code_id in code_ids:
            code = db.collection(code_type).document(code_id).get()
            experiments_ref = db.collection(
                f'{code_type}/{code_id}/channels/{channel_type}/experiments'
            )

            for snr in snr_range:
                experiments = list(
                    experiments_ref.where('snr_db', '==', snr).stream()
                )
                messages = (
                    required_messages -
                    sum([e.to_dict()['frames'] for e in experiments])
                )
                if messages <= 0:
                    continue

                result = code.to_dict()
                result.pop('M', None)
                result.pop('is_systematic', None)
                result['code_id'] = code.id
                result['code_type'] = code_type
                result['channel_type'] = channel_type
                result['messages'] = per_experiment
                result['snr'] = snr

                repetitions = ceil(messages / per_experiment)
                code_results = [result] * repetitions
                results += code_results

    return results


@app.route('/get-params', methods=['PUT'])
def get_params():
    """Get parameters for an experiment.
    Also, the parameter removed from list to be considered as already used.
    """
    try:
        experiments = list(PREPARED_COL_REF.order_by('N').limit(1).stream())

        if not experiments:
            return f'No params for experiments', 204

        experiment = experiments[0]
        response = experiment.to_dict()
        db.document(experiment.reference.path).delete()
        return jsonify(response), 200
    except Exception as e:
        return f'An Error Occurred: {e}\nRequest: {request.json}', 400


@app.route('/save-result', methods=['POST'])
def save_result():
    """Save experiment result for particular code."""
    try:
        result = request.json
        print(result)

        route_params = result.pop('route_params')
        code_type = route_params.get('code_type')
        code_id = route_params.get('code_id')
        channel_type = route_params.get('channel_type')

        experiments_ref = db.collection(
            f'{code_type}/{code_id}/channels/{channel_type}/experiments'
        )
        experiments_ref.add(result)

        return jsonify({"success": True}), 201
    except Exception as e:
        return f'An Error Occurred: {e}\nRequest: {request.json}', 400


@app.route('/clear', methods=['POST'])
def clear_collections():
    """Delete the data from collections."""
    try:
        to_clear = request.json['collections']
        results = dict()

        for coll in to_clear:
            deleted = 0

            while True:
                docs = list(db.collection(coll).limit(config.BATCH_SIZE).stream())

                if not docs:
                    break

                batch = db.batch()

                for doc in docs:
                    batch.delete(doc.reference)

                batch.commit()

                deleted += len(docs)

            results[coll] = deleted

        return jsonify(results), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/save-result', methods=['POST'])
def aggregate_results():
    """Aggregate experiment results."""


port = int(os.environ.get('PORT', 8080))
if __name__ == '__main__':
    app.run(threaded=True, host='0.0.0.0', port=port)
