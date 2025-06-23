import json
import pandas as pd
from llama_index.llms.gemini import Gemini
import csv

with open('config.json') as f:
    config = json.load(f)
llm_fast = Gemini(model="gemini-2.0-flash", api_key=config['gemini_api_key'])
llm_reasoning = Gemini(model="gemini-2.5-pro", api_key=config['gemini_api_key'])


def load_data(user_file='data/users.csv', content_file='data/contents_with_tags.csv', interaction_file='data/interactions.csv'):
    # Read users data and convert to dictionary
    # Each key is user_id and value is the list of interest tags
    users_df = pd.read_csv(user_file)
    users_dict = {
        row['user_id']: row['user_interest_tags']
        for _, row in users_df.iterrows()
    }

    # Read contents data and convert to dictionary
    # Each key is content_id and value is a dictionary containing title, intro, character_list, and initial_record
    contents_df = pd.read_csv(content_file)
    contents_dict = {
        row['content_id']: {
            'title': row['title'],
            'intro': row['intro'],
            'character_list': row['character_list'],
            'initial_record': row['initial_record'],
            **({'tags': row['tags']} if 'tags' in row.index else {})
        }
        for _, row in contents_df.iterrows()
    }

    # Read interactions data and convert to dictionary
    # Each key is user_id and value is a dictionary of content_id: interaction_count
    interactions_df = pd.read_csv(interaction_file)
    interactions_dict = {}
    for _, row in interactions_df.iterrows():
        user_id = int(row['user_id'])
        content_id = int(row['content_id'])
        count = int(row['interaction_count'])
        
        if user_id not in interactions_dict:
            interactions_dict[user_id] = {}
        
        interactions_dict[user_id][content_id] = count

    return users_dict, contents_dict, interactions_dict


def tag_contents(users_dict, contents_dict, interactions_dict):
    # For each user, get their tags and content interactions
    for user_id, user_tags in users_dict.items():

        print(user_id)
        
        # Skip if user has no interactions
        if user_id not in interactions_dict:
            continue
            
        # Get all content IDs this user interacted with
        content_interactions = interactions_dict[user_id]
        
        for content_id in content_interactions:
            if content_id not in contents_dict:
                continue
                
            content = contents_dict[content_id]
            
            # Construct prompt for LLM
            prompt = f"""Based on this content:
Title: {content['title']}
Intro: {content['intro']}
Characters: {content['character_list']}

And given that a user who likes: {user_tags}
Has interacted with this content {content_interactions[content_id]} times,

What tags would you assign to this content? Return as comma-separated list."""

            # Get tags from LLM
            response = llm_reasoning.complete(prompt)
            
            # Add tags to content dict if not already present
            if 'tags' not in content:
                content['tags'] = []
            
            # Add new tags, avoiding duplicates
            new_tags = [t.strip() for t in response.text.split(',')]
            content['tags'].extend([t for t in new_tags if t not in content['tags']])

    # Write contents with tags to a new CSV file
    with open("contents_with_tags.csv", "w", newline='', encoding="utf-8") as csvfile:
        fieldnames = ["content_id", "title", "intro", "character_list", "tags"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for cid, cdict in contents_dict.items():
            writer.writerow({
                "content_id": cid,
                "title": cdict.get("title", ""),
                "intro": cdict.get("intro", ""),
                "character_list": cdict.get("character_list", ""),
                "initial_record": cdict.get("initial_record", ""),
                "tags": ", ".join(cdict.get("tags", []))
            })


def index_contents(contents_dict):
# Start Generation Here
    tag_index = {}
    for content_id, content in contents_dict.items():
        content['content_id'] = content_id
        tags = content.get('tags', "")
        # If tags are stored as a single string, split by ','
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(',')]
            for tag in tags:
                if tag not in tag_index:
                    tag_index[tag] = []
                tag_index[tag].append(content)
    return tag_index
# End Generation Her