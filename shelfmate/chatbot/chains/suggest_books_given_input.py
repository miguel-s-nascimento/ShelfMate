from chatbot.chains.base import PromptTemplate, generate_prompt_templates 
from pydantic import BaseModel
from langchain.tools import BaseTool
from langchain.schema.runnable.base import Runnable
from langchain_community.chat_models import ChatOpenAI
from langchain.output_parsers import PydanticOutputParser
from typing import Type
from langchain_community.chat_models import ChatOpenAI
from langchain import callbacks
import sqlitecloud
import openai
from pinecone import Pinecone
from fuzzywuzzy import process


class WhichInput(BaseModel):
    which_input: str
    name: str


class ExtractInput(Runnable):
    def __init__(self, llm, memory= False):
        super().__init__()

        self.llm = llm

        prompt_template = PromptTemplate(
            system_template=""" 
            You are a part of a book recomendation system team.
            The user wants a book recommendation. 
            Your task if the user wants that recommendation to be based on a book, author or genre, by returning these words.
            Moreover, you have to extract the title of the book, name of the author or name of the genre.
            If you don't detect the specific author, genre or book, take into consideration the chat history with you and the user.


            Here is the user input:
            {user_input}

            Chat History:
            {chat_history}

            {format_instructions}
            """,
            human_template="user input: {user_input}",
        )

        self.prompt = generate_prompt_templates(prompt_template, memory=memory) 
        self.output_parser = PydanticOutputParser(pydantic_object=WhichInput)
        self.format_instructions = self.output_parser.get_format_instructions()

        self.chain = self.prompt | self.llm | self.output_parser

        con = sqlitecloud.connect("sqlitecloud://cikwryuhhz.g6.sqlite.cloud:8860/shelfmate.db?apikey=fxZSlHTpxWU109u7go8avF2RRHsZ43JUxDfarjdFpYg")
        cursor = con.cursor()
        cursor = con.cursor()
        cursor.execute("SELECT genre FROM genres")
        self.genres = [row[0] for row in cursor.fetchall()]
        cursor = con.cursor()
        cursor.execute("SELECT author_name FROM authors")
        self.authors = [row[0] for row in cursor.fetchall()]
        con.close()

    def invoke(self, inputs):
        result = self.chain.invoke(
            {
                "user_input": inputs["user_input"],
                "chat_history": inputs['chat_history'],
                "format_instructions": self.format_instructions,
            })

        if result.which_input == 'genre':
            closest_match, score = process.extractOne(result.name, self.genres)
            if score > 85:  
                result.name = closest_match
        elif result.which_input == 'author':
            closest_match, score = process.extractOne(result.name, self.authors)
            if score > 85:
                result.name = closest_match

        return result
    
#####################################################################################################################################


class SuggestBookOutput(BaseModel):
    output: str
    

class SuggestBooksGivenInputChain(Runnable):
    name: str = "SuggestBooksGivenInputChain" 
    description: str = "Suggest a book based on the user input"
    args_schema: Type[BaseModel] = SuggestBookOutput
    return_direct: bool = True

    def __init__(self, return_titles: bool = False, total_books: int = 5, memory: bool = True):
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        self.extract_chain = ExtractInput(self.llm)
        self.return_titles = return_titles
        self.total_books = total_books
        self.suggestions = None
        prompt_bot_return = PromptTemplate(
            system_template="""
            You are a part of the database manager team for a book recommendation platform called Shelfmate. 
            The user asked for book suggestions based on a specific author, genre or book. 

            Given the user input, the chat history and the suggestions generated, your task is to return to the user a message stating the suggestions in a friendly way \
            and guide the user to what more they can do on the platform. That includes adding books to their read list, adding genres \
            and authors to their favorites list, receiving suggestions of books and authors, and creating a reading plan. 
            Do not greet the user in the beggining of the message as this is already in the middle of the conversation.
            If the suggestions are empty it was not possible to recommend books according to the user input.
            
            User Input:
            {user_input}

            Suggestions:
            {suggestions}
            
            Chat History:
            {chat_history}

            {format_instructions}
            """,
            human_template="user input: {user_input}"
        )

        self.prompt = generate_prompt_templates(prompt_bot_return, memory=memory)
        self.output_parser = PydanticOutputParser(pydantic_object=SuggestBookOutput)
        self.format_instructions = self.output_parser.get_format_instructions()
        self.chain = (self.prompt | self.llm | self.output_parser).with_config({"run_name": self.__class__.__name__}) # adicionar isto do with_config

    def invoke(self, user_input, config):
        username = config.get('configurable').get('user_id')
        con = sqlitecloud.connect("sqlitecloud://cikwryuhhz.g6.sqlite.cloud:8860/shelfmate.db?apikey=fxZSlHTpxWU109u7go8avF2RRHsZ43JUxDfarjdFpYg")
        cursor = con.cursor()

        u_input = self.extract_chain.invoke(user_input)

        pinecone = Pinecone()
        index = pinecone.Index('books')
        
        if u_input.which_input == 'genre':
            genre_name = u_input.name
            cursor = con.cursor()
            cursor.execute("SELECT genre_id FROM genres WHERE genre LIKE ?", (genre_name,))
            genre_results = cursor.fetchall()
            
            if not genre_results:
                return "Genre not in the Database"

            genre_id = genre_results[0][0]
            query = """
            SELECT 
                b.title,
                GROUP_CONCAT(a.author_name, ', ') AS authors
            FROM books b
            INNER JOIN books_genres bg ON b.book_id = bg.book_id
            INNER JOIN authors_books ab ON b.book_id = ab.book_id
            INNER JOIN authors a ON ab.author_id = a.author_id
            LEFT JOIN read_list rl ON b.book_id = rl.book_id
            WHERE bg.genre_id = ? AND b.rating >= 4.7 AND rl.book_id IS NULL
            GROUP BY b.book_id
            ORDER BY RANDOM()
            LIMIT ?
            """
            cursor = con.cursor()
            cursor.execute(query, (genre_id, self.total_books, ))
            self.suggestions = cursor.fetchall()
            
            
        if u_input.which_input == 'author':
            author_name = u_input.name
            cursor = con.cursor()
            cursor.execute("SELECT author_id FROM authors WHERE author_name LIKE ?", (author_name,))
            author_results = cursor.fetchall()

            if not author_results:
                return "Author not in the Database"

            author_id = author_results[0][0]
            query = """
            SELECT 
                b.book_id, 
                b.title 
            FROM books b
            INNER JOIN authors_books ab ON b.book_id = ab.book_id
            INNER JOIN authors a ON ab.author_id = a.author_id
            LEFT JOIN read_list rl ON b.book_id = rl.book_id
            WHERE a.author_id = ? AND rl.book_id IS NULL
            GROUP BY b.book_id
            ORDER BY RANDOM()
            LIMIT ?
            """
            cursor = con.cursor()
            cursor.execute(query, (author_id, self.total_books,))
            self.suggestions = cursor.fetchall()
            
        if u_input.which_input == 'book':
            title = u_input.name
            embedding = openai.embeddings.create(model="text-embedding-ada-002",
                                                input=[title]).data[0].embedding

            filter_condition = {"type": {"$eq": "title"}}
            search_results = index.query(
                vector=embedding,
                top_k=1,
                include_metadata=True,
                filter=filter_condition)

            book_id = int(search_results['matches'][0]['metadata']['book_id'])

            fetch_results = index.fetch(ids=['desc_' + str(book_id)])
            desc_embedding = fetch_results.vectors['desc_' + str(book_id)].values

            filter_condition = {"book_id": {"$nin": [book_id]}, "type": {"$eq": "description"}}
            search_results = index.query(
                vector=desc_embedding,
                top_k=5,
                include_metadata=True,
                filter=filter_condition)

            all_ids = [int(search_results['matches'][i]['metadata']['book_id']) for i in range(5)]

            # Ensure we exclude books already in the read list
            query = """
            SELECT 
                b.title,
                GROUP_CONCAT(a.author_name, ', ') AS authors
            FROM books b
            INNER JOIN authors_books ab ON b.book_id = ab.book_id
            INNER JOIN authors a ON ab.author_id = a.author_id
            LEFT JOIN read_list rl ON b.book_id = rl.book_id
            WHERE b.book_id IN ({}) AND rl.book_id IS NULL
            GROUP BY b.book_id
            """.format(','.join('?' for _ in all_ids))
            cursor = con.cursor()
            cursor.execute(query, all_ids)
            self.suggestions = cursor.fetchall()
            
        con.close()
        
        if self.return_titles:
            return self.suggestions

        response = self.chain.invoke({ # gerar a resposta do bot de acordo com o outcome da situação
            "user_input": user_input['user_input'],
            'chat_history': user_input['chat_history'], # passar o chat_history
            "suggestions": self.suggestions,
            "format_instructions": self.format_instructions
        })

        return response.output