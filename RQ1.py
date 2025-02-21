import os
os.environ['HF_HOME'] = '<Path for HF cache>'

from transformers import pipeline
from transformers import AutoTokenizer
from huggingface_hub import login
import argparse
import pandas as pd
import ast
from tqdm import tqdm
import json
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from datasets import Dataset
import random
import numpy as np
import torch

access_token = "<HF token here>"
login(token = access_token)

def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
set_seed(42)

label2idx = {'a': 'a', 'b': 'b', '1': 'a', '2': 'b', 1: 'a', 2: 'b'}
idx2moral = ['Care', 'Equality', 'Proportionality', 'Loyalty', 'Authority', 'Purity']
idx2culture = ['Power Distance', 'Individualism', 'Motivation', 'Uncertainty Avoidance', 'Long Term Orientation', 'Indulgence']

def dict_to_list_of_vectors(data):
    data = ast.literal_eval(data)
    return list(data.values())

def read_data_RQ1(data_file_long, data_file_short):
    print("Reading data...")
    data = pd.read_csv(data_file_long)
    data_short = pd.read_csv(data_file_short)
    data = pd.concat([data, data_short], ignore_index=True)
    data = data[['Scenario_id', 'Annotator_id', 'Scenario', 'Possible_actions', 'Selected_action', 'Moral_values', 'Cultural_values', 'Annotator_self_description']]
    print("Data read -- ", len(data), "\n", data.columns, "\n", data.head())

    main_data = []
    for i in tqdm(range(len(data))):
        moral_vector = dict_to_list_of_vectors(data['Moral_values'][i])
        culture_vector = dict_to_list_of_vectors(data['Cultural_values'][i])

        moral_idx = sorted(range(len(moral_vector)), key=lambda i: moral_vector[i], reverse=True)
        culture_idx = sorted(range(len(culture_vector)), key=lambda i: culture_vector[i], reverse=True)

        this_inst = {
            'scenario_id': data['Scenario_id'][i],
            'annotator_id': data['Annotator_id'][i],
            'scenario': data['Scenario'][i],
            'actions': data['Possible_actions'][i],
            'gt': label2idx[data['Selected_action'][i]],
            'desc': data['Annotator_self_description'][i],
            'moral_vector': moral_vector,
            'culture_vector': culture_vector,
            'moral_idx': [idx2moral[x] for x in moral_idx],
            'culture_idx': [idx2culture[x] for x in culture_idx]

        }
        main_data.append(this_inst)

    cnt = 0
    for inst in main_data:
        annotator = inst['annotator_id']
        annotator_data = data[data['Annotator_id'] == annotator]
        annotator_data = annotator_data[annotator_data['Scenario_id'] != inst['scenario_id']]
        try:
            annotator_data = annotator_data.sample(n=3, replace=True, random_state=42)
        except:
            cnt += 1
            annotator_data = data[data['Annotator_id'] == annotator]
            annotator_data = annotator_data.sample(n=3, replace=True, random_state=42)
        annotator_data = annotator_data.reset_index(drop=True)
        fs_scenarios, fs_actions, fs_gt = [], [], []
        for i in range(len(annotator_data)):
            fs_scenarios.append(annotator_data['Scenario'][i])
            fs_possible_actions = ast.literal_eval(annotator_data['Possible_actions'][i])
            if type(fs_possible_actions[0]) != str:
                fs_actions.append("(a) " + fs_possible_actions[0][0] + "; (b) " + fs_possible_actions[1][0])
            else:
                fs_actions.append("(a) " + fs_possible_actions[0] + "; (b) " + fs_possible_actions[1])
                
            fs_gt.append(label2idx[annotator_data['Selected_action'][i]])
        inst['fs_scenarios'] = fs_scenarios
        inst['fs_actions'] = fs_actions
        inst['fs_gt'] = fs_gt

    print("cnt: ", cnt)

    return main_data

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='meta-llama/Meta-Llama-3.1-8B-Instruct', type=str, help='Model name for pipeline')
    parser.add_argument('--language', default='English', type=str, help='Language out of ["English", "Chinese", "Russian", "Arabic", "Spanish", and "Hindi"]')
    parser.add_argument('--mode', default='desc', type=str, help='Mode out of ["desc", "moral", "culture", "fs", "np"]')
    parser.add_argument('--batch_size', default=4, type=int, help='Batch size used for generation')
    args = parser.parse_args()

    RQ = 1
    mode = args.mode
    language = args.language
    model_name = args.model
    batch_size = args.batch_size

    with open("PROMPTS.txt", "r") as f:
        PROMPTS = f.read()
    PROMPTS = ast.literal_eval(PROMPTS)

    pipe = pipeline("text-generation", model=model_name, device_map="auto", truncation=True)

    data_file_rq123 = f"Final_data/{language}_long.csv"
    data_file_rq1 = f"Final_data/{language}_short.csv"

    data = read_data_RQ1(data_file_rq123, data_file_rq1)

    formatted_prompts = []
    ground_truth = []
    predictions = []

    for i, inst in tqdm(enumerate(data)):
        ground_truth.append(inst['gt'])

        possible_actions = ast.literal_eval(inst['actions'])
        if type(possible_actions[0]) != str:
            possible_actions = "(a) " + possible_actions[0][0] + "; (b) " + possible_actions[1][0]
        else:
            possible_actions = "(a) " + possible_actions[0] + "; (b) " + possible_actions[1]
        
        prompt = PROMPTS[f"prompt_{mode}_{language.lower()[:3]}_rq{RQ}"]
        
        prompt = prompt.replace("[SCENARIO]", inst['scenario'])
        prompt = prompt.replace("[ACTIONS]", possible_actions)
        prompt = prompt.replace("[DESC]", inst['desc'])
        prompt = prompt.replace("[MORAL]", " ".join(map(str,inst['moral_vector'])))
        prompt = prompt.replace("[CULTURE]", " ".join(map(str,inst['culture_vector'])))

        prompt = prompt.replace("[MORAL_VALUE_1]", inst['moral_idx'][0])
        prompt = prompt.replace("[MORAL_VALUE_2]", inst['moral_idx'][1])
        prompt = prompt.replace("[MORAL_VALUE_3]", inst['moral_idx'][2])
        prompt = prompt.replace("[MORAL_VALUE_4]", inst['moral_idx'][3])
        prompt = prompt.replace("[MORAL_VALUE_5]", inst['moral_idx'][4])
        prompt = prompt.replace("[MORAL_VALUE_6]", inst['moral_idx'][5])
        
        prompt = prompt.replace("[CULTURAL_VALUE_1]", inst['culture_idx'][0])
        prompt = prompt.replace("[CULTURAL_VALUE_2]", inst['culture_idx'][1])
        prompt = prompt.replace("[CULTURAL_VALUE_3]", inst['culture_idx'][2])
        prompt = prompt.replace("[CULTURAL_VALUE_4]", inst['culture_idx'][3])
        prompt = prompt.replace("[CULTURAL_VALUE_5]", inst['culture_idx'][4])
        prompt = prompt.replace("[CULTURAL_VALUE_6]", inst['culture_idx'][5])

        prompt = prompt.replace("[FS_SCENARIO_1]", inst['fs_scenarios'][0])
        prompt = prompt.replace("[FS_ACTIONS_1]", inst['fs_actions'][0])
        prompt = prompt.replace("[FS_GT_1]", inst['fs_gt'][0])
        prompt = prompt.replace("[FS_SCENARIO_2]", inst['fs_scenarios'][1])
        prompt = prompt.replace("[FS_ACTIONS_2]", inst['fs_actions'][1])
        prompt = prompt.replace("[FS_GT_2]", inst['fs_gt'][1])
        prompt = prompt.replace("[FS_SCENARIO_3]", inst['fs_scenarios'][2])
        prompt = prompt.replace("[FS_ACTIONS_3]", inst['fs_actions'][2])
        prompt = prompt.replace("[FS_GT_3]", inst['fs_gt'][2])

        formatted_prompt = formatted_prompt = f"""
            ### Instruction:
            {prompt}

            ### Response:
        """

        if i == 0:
            print("Example prompt: ", formatted_prompt)

        formatted_prompts.append(formatted_prompt)

    print("\nGenerating responses...")
    generated_outputs = []
    for i in tqdm(range(0, len(formatted_prompts), batch_size), desc="Generating batches"):
        batch = formatted_prompts[i:i+batch_size]
        outputs = pipe(
            batch
        )
        generated_outputs.extend(outputs)

    unsure_preds = 0
    predictions = []
    for output in generated_outputs:
        generated_text = output[0]['generated_text']
        generated_text = generated_text.split("### Response:")[1].strip()
        try:
            generated_text = generated_text.split("Selected action is ")[1].strip()
        except:
            unsure_preds += 1
            print("generated_text: ", generated_text)
            generated_text = generated_text
        response = generated_text.lower().strip()

        if RQ == 1:
            pred = 'a' if 'a' in response else 'b'
        predictions.append(pred)

    ground_truth = [1 if x == 'a' else 2 for x in ground_truth]
    predictions = [1 if x == 'a' else 2 for x in predictions]

    print(ground_truth, predictions)
    accuracy = accuracy_score(ground_truth, predictions)
    precision = precision_score(ground_truth, predictions)
    recall = recall_score(ground_truth, predictions)
    f1 = f1_score(ground_truth, predictions)

    results = {
        'predictions': predictions,
        'ground truth': ground_truth,
        'accuracy': accuracy,
        'precision': precision,
        'recall': recall,
        'f1 score': f1
    }

    print(f"Accuracy: {accuracy}")
    print(f"Precision: {precision}")
    print(f"Recall: {recall}")
    print(f"F1 Score: {f1}")

    with open(f"Final_results/{language}_RQ{RQ}_{mode}_{model_name.split('/')[-1]}.json","w") as f:
        json.dump(results, f)