from chatbot.chains.base import PromptTemplate, generate_prompt_templates
from langchain.schema.runnable.base import Runnable
from langchain_community.chat_models import ChatOpenAI
from langchain.agents import Tool
from langchain.agents import AgentExecutor
from langchain.tools import BaseTool
from langchain.output_parsers import PydanticOutputParser
from langchain_community.utilities.sql_database import SQLDatabase
from fuzzywuzzy import process
from pydantic import BaseModel
from typing import Type
import sqlitecloud  

class QueryType(BaseModel):
    query_type: str
    value: str
    num_results: int = 5  # Default to 5 results if not specified


# Define ExtractQueryType class
class ExtractQueryType(Runnable):
    def __init__(self, llm, memory=False):
        super().__init__()
        self.llm = llm

        # Create a prompt template instance
        prompt_template = PromptTemplate(
            system_template=
            """ 
            You are part of a database management team for a book recommendation platform called Shelfmate.
            Given the user input, your task is to identify the type of query the user wants to perform and its value.

            If the user wants to know which genres are available in the database, return query_type='list_genres' and value=0.
            If the user wants to know authors that write predominantly in a specific genre: query_type='authors_by_genre' and value= the specific genre the user wants.
            If the user wants to know which books are available for a specific genre, return query_type='books_by_genre' and value= the specific genre the user wants.
            If the user wants to know which books are available written by a specific author, return query_type='books_by_author' abd value= the specific author the user wants.

            If the user input contains 'all' or 'every' authors or genres, return num_results as 20. If ambiguous, return 5.
            You can also take into consideration the chat history with you and the user.

            Here is the user input:
            {user_input}

            Chat History:
            {chat_history}

            {format_instructions}
            """, human_template="user input: {user_input}"
        )

        
        self.prompt = generate_prompt_templates(prompt_template, memory=memory)
        self.output_parser = PydanticOutputParser(pydantic_object=QueryType)
        self.format_instructions = self.output_parser.get_format_instructions()

        self.chain = self.prompt | self.llm | self.output_parser

        con = sqlitecloud.connect("sqlitecloud://cikwryuhhz.g6.sqlite.cloud:8860/shelfmate.db?apikey=fxZSlHTpxWU109u7go8avF2RRHsZ43JUxDfarjdFpYg")
        cursor = con.cursor()
        cursor.execute("SELECT genre FROM genres")
        self.genres = [row[0] for row in cursor.fetchall()]
        cursor = con.cursor()
        cursor.execute("SELECT author_name FROM authors")
        self.authors = [row[0] for row in cursor.fetchall()]
        con.close()

    def invoke(self, inputs):
        # Pass user input and format instructions to the chain
        result = self.chain.invoke({
            "user_input": inputs["user_input"],
            "chat_history": inputs["chat_history"],
            "format_instructions": self.format_instructions
        })

        # Perform fuzzy matching for genres or authors
        if result.query_type in ['authors_by_genre', 'books_by_genre']:
            closest_match, score = process.extractOne(result.value, self.genres)
            if score > 80:  # Adjust the threshold as needed
                result.value = closest_match
        elif result.query_type == 'books_by_author':
            closest_match, score = process.extractOne(result.value, self.authors)
            if score > 80:
                result.value = closest_match

        return result
##########################################################################################################
    
class Output(BaseModel):
    output:str

class BrowserChain(Runnable):
    name: str = "BrowserChain"
    description: str = (
        "Queries the database for genres, authors, or books based on user input, "
        "given the number of results requested. Return a phrase and not a list."
    )
    args_schema: Type[BaseModel] = QueryType
    return_direct: bool = True

    def __init__(self, memory=True) -> str:
        # Initialize the LLM and extract query information
        self.llm = ChatOpenAI(model="gpt-4o-mini")
        self.extract_chain = ExtractQueryType(self.llm)

        prompt_bot_return = PromptTemplate(
            system_template = """
            You are a part of the database manager team for a book recommendation platform called Shelfmate. 
            The user asked for a list of books according to a genre or author, a list of authors based on a specific genre or a list of genres. 
            There are 3 possible outcomes:
            - The information was successfully extracted (status is the retrieved list with the informations asked).
            - There was an error extracting the information (status contains informations about the error).
            
            Given the user input, the chat history and the status, your task is to return to the user a message stating the result of the operation in a friendly way \
            and guide the user to what more they can do on the platform. That includes adding books to their read list, adding genres \
            and authors to their favorites list, receiving suggestions of books and authors, and creating a reading plan.
            Do not greet the user in the beggining of the message as this is already in the middle of the conversation.
            
            Here is the user input:
            {user_input}

            Chat History:
            {chat_history}
            
            Status:
            {status}

            {format_instructions}
            """,
            human_template = "user input: {user_input}"
        )

        self.prompt = generate_prompt_templates(prompt_bot_return, memory=memory)
        self.output_parser = PydanticOutputParser(pydantic_object=Output)
        self.format_instructions = self.output_parser.get_format_instructions()
        self.chain = (self.prompt | self.llm | self.output_parser).with_config({"run_name": self.__class__.__name__})
    
    def invoke(self, user_input, config):
        # Define the database path and connect
        con = sqlitecloud.connect("sqlitecloud://cikwryuhhz.g6.sqlite.cloud:8860/shelfmate.db?apikey=fxZSlHTpxWU109u7go8avF2RRHsZ43JUxDfarjdFpYg")
        cursor = con.cursor()

        try:
            query_info = self.extract_chain.invoke(user_input)
            num_results = query_info.num_results

            # Handle 'list_genres' query type
            if query_info.query_type == 'list_genres':
                query = f"SELECT genre FROM genres LIMIT {num_results}"
                results = cursor.execute(query).fetchall()
                if not results:
                    self.status = "It was not possible to find any genres. Double-check the genre name or try a different query."
                results_str = str(results).strip("[()]\"").replace(",)", "").replace("(", "").strip(",\"")
                self.status =  f"Genres: {results_str}. Let me know if you want more suggestions"

            # Handle 'authors_by_genre' query type
            elif query_info.query_type == 'authors_by_genre':
                genre = query_info.value
                query = f"""
                    SELECT a.author_name FROM authors a 
                    JOIN genres g ON a.top_genre = g.genre_id 
                    WHERE g.genre = '{genre}' ORDER BY RANDOM() LIMIT {num_results}"""
                
                cursor = con.cursor()
                results = cursor.execute(query).fetchall()
                if not results:
                    self.status = f"It was not possible to find any authors for the genre '{genre}'. Please check the spelling or try another genre."
                results_str = str(results).strip("[()]\"").replace(",)", "").replace("(", "").strip(",\"")
                self.status =  f"Writers who write in the '{genre}' genre: {results_str}. Would you like more recommendations?"

            # Handle 'books_by_genre' query type
            elif query_info.query_type == 'books_by_genre':
                genre = query_info.value
                query = f"""
                    SELECT b.title FROM books b 
                    JOIN books_genres bg ON b.book_id = bg.book_id 
                    JOIN genres g ON bg.genre_id = g.genre_id 
                    WHERE g.genre = '{genre}' ORDER BY RANDOM() LIMIT {num_results}"""

                cursor = con.cursor()
                results = cursor.execute(query).fetchall()
                if not results:
                    self.status = f"It was not possible to find any books for the genre '{genre}' in our collection. You can try another genre or let me know if you need suggestions."
                results_str = str(results).strip("[()]\"").replace(",)", "").replace("(", "").strip(",\"")
                self.status = f"Books from the '{genre}' genre: {results_str}. Let me know if you'd like more book recommendations."

            # Handle 'books_by_author' query type
            elif query_info.query_type == 'books_by_author':
                author = query_info.value
                query = f"""
                    SELECT b.title FROM books b 
                    JOIN authors_books ab ON b.book_id = ab.book_id 
                    JOIN authors a ON ab.author_id = a.author_id 
                    WHERE a.author_name = '{author}' ORDER BY RANDOM() LIMIT {num_results}"""
                
                cursor = con.cursor()
                results = cursor.execute(query).fetchall()
                if not results:
                    self.status = f"It was not possible to find any books by the author '{author}'. Perhaps you'd like to try a different author or genre?"
                results_str = str(results).strip("[()]\"").replace(",)", "").replace("(", "").strip(",\"")
                self.status = f"Books written by '{author}': {results_str}. Let me know if you'd like more options or have a specific book in mind."

            # Handle invalid query types
            else:
                self.status = "Input not understandable"

        except Exception as e:
            return f"Error: {e}"

        response =  self.chain.invoke({
            "user_input": user_input['user_input'],
            'chat_history': user_input['chat_history'],
            "status": self.status,
            "format_instructions": self.format_instructions
        })

        return response.output
