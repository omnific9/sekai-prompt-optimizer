from llama_index.core.workflow import Context
from llama_index.core.agent.workflow import (
    AgentInput,
    AgentOutput,
    ToolCall,
    ToolCallResult,
    AgentStream,
    AgentWorkflow,
    FunctionAgent,
)
import asyncio, random, time
from utils import load_data, tag_contents, index_contents,llm_fast, llm_reasoning
from typing import List, Any

# Use the following to generate tags for contents
# users_dict, contents_dict, interactions_dict = load_data(user_file='data/users.csv', content_file='data/contents.csv', interaction_file='data/interactions.csv')
# contents_dict = tag_contents(users_dict, contents_dict, interactions_dict)

users_dict, contents_dict, interactions_dict = load_data()
tagged_contents_dict = index_contents(contents_dict)
state = {
    "prompts": ["You are given a user's preference tags and a list of stories. Recommend stories that the user will most likely enjoy."],
    "scores": [],
    "feedbacks": [],
    "ground_truth": [],
    "recommendations": [],
}

async def get_feedback(ctx: Context) -> str:
    feedbacks = state["feedbacks"]
    if len(feedbacks) == 0:
        return ""
    return feedbacks[-1]

async def get_prompt(ctx: Context) -> str:
    current_prompt = state["prompts"][-1]
    return current_prompt

async def update_prompt(ctx: Context, prompt: str) -> str:
    state["prompts"].append(prompt)
    return f"New prompt: {prompt}"

async def get_full_user_profile(ctx: Context) -> str:
    current_state = await ctx.get("state")
    # Select a random user_id from users_dict
    user_id = random.choice(list(users_dict.keys()))
    user_profile = users_dict[user_id]
    current_state["user_id"] = user_id
    current_state["user_profile"] = user_profile
    await ctx.set("state", current_state)
    return {"user_id": user_id, "profile": user_profile}

async def store_new_user_tags(ctx: Context, tags: List[str]) -> str:
    current_state = await ctx.get("state")
    current_state["new_user_tags"] = tags
    await ctx.set("state", current_state)
    return f"Stored {len(tags)} new user tags"

async def get_user_and_stories(ctx: Context) -> str:
    current_state = await ctx.get("state")
    user_profile = current_state["user_profile"]
    return {"user_profile": user_profile, "contents": contents_dict}

async def store_ground_truth(ctx: Context, ground_truth: List[int]) -> str:
    current_state = await ctx.get("state")
    if hasattr(ground_truth, '_pb'):
        ground_truth = list(ground_truth)
    current_state["ground_truth"] = ground_truth
    await ctx.set("state", current_state)
    state["ground_truth"] = ground_truth
    return f"Stored {len(ground_truth)} ground truth recommendations"

async def get_contents_by_tags(ctx: Context, tags: List[str]) -> List[Any]:
    selected_contents = []
    for tag in tags:
        if tag in tagged_contents_dict:
            simplified_contents = [
                {"content_id": content['content_id'], 
                 "title": content['title'], 
                 "intro": content['intro'], 
                 "character_list": content['character_list'], 
                 "tags": content['tags']} for content in tagged_contents_dict[tag]
            ]
            selected_contents.extend(simplified_contents)
    return selected_contents

async def store_recommendations(ctx: Context, recommendations: List[int]) -> str:
    current_state = await ctx.get("state")
    if hasattr(recommendations, '_pb'):
        recommendations = list(recommendations)
    current_state["recommendations"] = recommendations
    state["recommendations"] = recommendations
    await ctx.set("state", current_state)
    return f"Stored {len(recommendations)} recommendations"

async def get_recommendations(ctx: Context) -> List[Any]:
    current_state = await ctx.get("state")
    return current_state.get("recommendations", [])

async def get_recommendations_and_ground_truth(ctx: Context) -> str:
    current_state = await ctx.get("state")
    recommendations = current_state.get("recommendations", [])
    ground_truth = current_state.get("ground_truth", [])
    recommended_stories = [content for tag in tagged_contents_dict for content in tagged_contents_dict[tag] if content['content_id'] in recommendations]
    ground_truth_stories = [content for tag in tagged_contents_dict for content in tagged_contents_dict[tag] if content['content_id'] in ground_truth]
    prompt = state["prompts"][-1]
    # Compute precision@10
    recommended_set = set(recommendations)
    ground_truth_set = set(ground_truth)
    hits = recommended_set & ground_truth_set
    score = len(hits) / 10
    state["scores"].append(score)
    return f"Recommended stories: {recommended_stories}\n generated from f{prompt}\nGround truth stories: {ground_truth_stories}\nPrompt: {prompt}\Precision: {score}"

async def store_feedback(ctx: Context, feedback: str) -> str:
    state["feedbacks"].append(feedback)
    return f"Stored feedback: {feedback}"

async def main():
    base_delay = 1  # seconds
    max_delay = 30  # seconds, can be set to a high value if desired
    attempt = 0
    start_time = time.time()
    time_limit = 5 * 60  # 5 minutes in seconds
    minimum_score = 0.8
    while True:
        try:
            prompt_optimizer_agent = FunctionAgent(
                name="PromptOptimizerAgent",
                description="Useful for optimizing the prompt",
                system_prompt=(
                    "You are the PromptOptimizerAgent that can optimize the prompt."
                    "Your goal is to optimize the prompt that can recommend the best stories for users based on their interests. "
                    "The users are looking for stories that fulfill their roleplaying fantasies."
                    "You may use get_prompt to see the current prompt."
                    "You may also use get_feedback to see the feedback given for the current prompt, if there is any."
                    "Once you generate a new promp based on the feedback, you may use update_prompt to update the prompt for the recommendation agent."
                    "You must hand off control to the SimulationAgent after updating the prompt."
                ),
                llm=llm_fast,
                tools=[get_prompt, update_prompt, get_feedback],
                can_handoff_to=["SimulationAgent"],
            )

            simulation_agent = FunctionAgent(
                name="SimulationAgent",
                description="Useful for evaluating the quality of the recommendations",
                system_prompt=(
                    "You are the SimulationAgent that simulates a new user and creates ground truth for evaluation."
                    "You will first use get_full_user_profile to get a user and their full profile."
                    "You will then pick 5 of the user's tags that are the most likely to be the user's initial interests that they select from a sign-up page."
                    "Store these tags in the store_new_user_tags tool."
                    "You must hand off control to the GroundTruthAgent after storing the new user tags."
                ),
                llm=llm_fast,
                tools=[get_full_user_profile, store_new_user_tags],
                can_handoff_to=["GroundTruthAgent"],
            )

            ground_truth_agent = FunctionAgent(
                name="GroundTruthAgent",
                description="Useful for generating ground truth for evaluation",
                system_prompt=(
                    "You are the GroundTruthAgent that can generate ground truth for evaluation."
                    "Use get_user_and_stories to get the target user's preferences and all the stories in the database."
                    "Think carefully and recommend 10 stories that the user will most likely enjoy. Give only the story IDs, no other text."
                    "Store these recommendations in the store_ground_truth tool."
                    "You must hand off control to the RecommendationAgent after storing the ground truth."
                ),
                llm=llm_reasoning,
                tools=[get_user_and_stories, store_ground_truth],
                can_handoff_to=["RecommendationAgent"],
            )

            recommendation_agent = FunctionAgent(
                name="RecommendationAgent",
                description="Useful for recommending stories to users based on their interests",
                system_prompt=(
                    "You are the RecommendationAgent that can recommend 10 stories to users based on their interests. "
                    "You must use get_contents_by_tags to get the potential stories that match the tags: slice of life, romance, naruto."
                    "Once you have the recommended stories, you must also store the recommended story IDs in the context using store_recommendations."
                    "Give only the story IDs, no other text. Once you're done, you must hand off control to the EvaluationAgent.\n" + state["prompts"][-1]
                ),
                llm=llm_fast,
                tools=[get_contents_by_tags, store_recommendations],
                can_handoff_to=["EvaluationAgent"],
            )

            evaluation_agent = FunctionAgent(
                name="EvaluationAgent",
                description="Useful for evaluating the quality of the recommendations",
                system_prompt=(
                    "You are the EvaluationAgent that can evaluate the quality of the recommendations."
                    "You must use get_recommendations_and_ground_truth to get the prompt that generated the recommendations, the recommended stories and ground truth."
                    "Based on this information, you must generate a feedback for human to improve the prompt."
                    "You must then store the feedback using the store_feedback tool."
                    "Once you store the feedback, do not hand off control to any other agent. Simply exit."
                ),
                llm=llm_reasoning,
                tools=[get_recommendations_and_ground_truth, store_feedback],
            )

            agent_workflow = AgentWorkflow(
                agents=[prompt_optimizer_agent, simulation_agent, ground_truth_agent, recommendation_agent, evaluation_agent],
                root_agent=prompt_optimizer_agent.name,
                initial_state={},
            )

            handler = agent_workflow.run(user_msg="")
            current_agent = None
            async for event in handler.stream_events():
                if (
                    hasattr(event, "current_agent_name")
                    and event.current_agent_name != current_agent
                ):
                    current_agent = event.current_agent_name
                    print(f"\n{'='*50}")
                    print(f"🤖 Agent: {current_agent}")
                    print(f"{'='*50}\n")

                # if isinstance(event, AgentStream):
                #     if event.delta:
                #         print(event.delta, end="", flush=True)
                # elif isinstance(event, AgentInput):
                #     print("📥 Input:", event.input)
                elif isinstance(event, AgentOutput):
                    if event.response.content:
                        print("📤 Output:", event.response.content)
                    if event.tool_calls:
                        print(
                            "🛠️  Planning to use tools:",
                            [call.tool_name for call in event.tool_calls],
                        )
                # elif isinstance(event, ToolCallResult):
                #     print(f"🔧 Tool Result ({event.tool_name}):")
                #     print(f"  Arguments: {event.tool_kwargs}")
                #     print(f"  Output: {event.tool_output}")
                # elif isinstance(event, ToolCall):
                #     print(f"🔨 Calling Tool: {event.tool_name}")
                #     print(f"  With arguments: {event.tool_kwargs}")
            print("State: ", state)
        except Exception as e:
            attempt += 1
            # Exponential backoff with jitter
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            jitter = random.uniform(0, delay * 0.5)
            total_delay = delay + jitter
            print(f"Error occurred: {e}. Retrying in {total_delay:.2f} seconds (attempt {attempt})...")
            await asyncio.sleep(total_delay)
        end_time = time.time()
        if end_time - start_time > time_limit:
            break
        if len(state["scores"]) > 0 and state["scores"][-1] >= minimum_score:
            break
        print("State: ", state)



if __name__ == "__main__":
    asyncio.run(main())