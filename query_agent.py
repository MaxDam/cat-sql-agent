from langchain.agents import create_sql_agent, create_json_agent
#from langchain.agents import create_csv_agent
from langchain_experimental.agents.agent_toolkits.csv.base import create_csv_agent
from langchain.agents.agent_toolkits import SQLDatabaseToolkit 
from langchain.sql_database import SQLDatabase 
from langchain.agents.agent_types import AgentType
from langchain.tools.json.tool import JsonSpec
from langchain.agents.agent_toolkits import JsonToolkit
from cat.looking_glass.prompts import MAIN_PROMPT_PREFIX
from .settings import datasources
from cat.log import log
import json


class QueryCatAgent:

    def __init__(self, cat):
        self.cat = cat
        
        # Acquire all settings
        self.settings = cat.mad_hatter.get_plugin().load_settings()

        # Get user message
        self.user_message = cat.working_memory["user_message_json"]["text"]


    # Execute agent to get a final thought, based on the type 
    def get_reasoning_agent(self) -> str:
        
        # Set input prompt from settings
        self.input_prompt = self.user_message
        if self.settings["input_prompt"] != '':
            self.input_prompt = self.settings["input_prompt"].format(
                user_message=self.user_message
            )
        print("=====================================================")
        print(f"Input prompt:\n{self.input_prompt}")
        print("=====================================================")

        # Get agent type
        datasource_type = self.settings["ds_type"]
        agent_type = datasources[datasource_type]["agent_type"]

        # Execute agent based on the type
        if agent_type == "sql":
            return self._get_reasoning_sql_agent()
        if agent_type == "csv":
            return self._get_reasoning_csv_agent()
        if agent_type == "json":
            return self._get_reasoning_json_agent()
        
        return ""


    # Return final response, based on the user's message and reasoning
    def get_final_output(self, thought):

        # Get prompt
        prompt_prefix = self.cat.mad_hatter.execute_hook("agent_prompt_prefix", MAIN_PROMPT_PREFIX, cat=self.cat)

        # Get user message and chat history
        chat_history = self.cat.agent_manager.agent_prompt_chat_history(
            self.cat.working_memory["history"]
        )

        # Default output Prompt
        output_prompt = f"""{prompt_prefix}
        You have elaborated the user's question, 
        you have searched for the answer and now you 
        have the solution in your Thought; 
        reply to the user briefly, 
        precisely and based on the context 
        of the dialogue.
        - Human: {self.user_message}
        - Thought: {thought}
        - AI:"""

        # Set output prompt from settings
        if self.settings["output_prompt"] != '':
            output_prompt = self.settings["output_prompt"].format(
                prompt_prefix = prompt_prefix, 
                user_message  = self.user_message, 
                thought       = thought, 
                chat_history  = chat_history
            )

        # Invoke LLM and obtain final and contestual response
        print("=====================================================")
        print(f"Output prompt:\n{output_prompt}")
        print("=====================================================")
        return self.cat.llm(output_prompt)


    # Execute sql agent
    def _get_reasoning_sql_agent(self):

        # Create connection string
        datasource_type = self.settings["ds_type"]
        connection_string = datasources[datasource_type]["conn_str"].format(**self.settings)
        log.warning(f"Connection string: {connection_string}")

        # Create sql connection
        try:
            db = SQLDatabase.from_uri(connection_string)

            # Create SQL DB Toolkit
            sqldbtlk = SQLDatabaseToolkit(db=db, llm=self.cat._llm)

            # Create SQL Agent
            agent_executor = create_sql_agent(
                llm=self.cat._llm,
                toolkit=sqldbtlk,
                verbose=True,
                agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            )
        except Exception as e:
            log.error(f"Failed to create SQL connection: {e}")
            return f"it was not possible to connect to the selected data source: {e}"

        # Obtain final thought, after agent reasoning steps
        final_thought = agent_executor.run(self.input_prompt)
        return final_thought


    # Execute csv agent
    def _get_reasoning_csv_agent(self):

        # Get csv file path
        csv_file_path = self.settings["host"]
        delimiter = self.settings["extra"] if self.settings["extra"].strip() else ";"

        # Create CSV agent
        try:
            #agent_executor = create_csv_agent(cat._llm, csv_file_path, verbose=True)
            agent_executor = create_csv_agent(self.cat._llm, csv_file_path, pandas_kwargs={'delimiter': delimiter}, verbose=True)
        except Exception as e:
            log.error(f"Failed to create SQL connection: {e}")
            return f"it was not possible to connect to the selected data source: {e}"

        # Obtain final thought, after agent reasoning steps
        final_thought = agent_executor.run(self.input_prompt)
        return final_thought


    # Execute json agent
    def _get_reasoning_json_agent(self):

        # Get json file path
        json_file_path = self.settings["host"]

        # Get json data
        with open(json_file_path, 'r') as reader:
            data = json.load(reader)

        # Create JSON toolkit
        json_spec = JsonSpec(dict_= data, max_value_length=4000)
        json_toolkit = JsonToolkit(spec=json_spec)

        # Create JSON agent
        try:
            agent_executor = create_json_agent(
                llm=self.cat._llm,
                toolkit=json_toolkit,
                verbose=True
            )
        except Exception as e:
            log.error(f"Failed to create SQL connection: {e}")
            return f"it was not possible to connect to the selected data source: {e}"

        # Obtain final thought, after agent reasoning steps
        final_thought = agent_executor.run(self.input_prompt)
        return final_thought
