from chatbot.chains.base import PromptTemplate, generate_prompt_templates 
from chatbot.chains.suggest_books_given_favourites import SuggestBooksGivenFavChain
from chatbot.chains.suggest_books_given_input import SuggestBooksGivenInputChain
from pydantic import BaseModel
from langchain.tools import BaseTool
from langchain.schema.runnable.base import Runnable
from langchain_community.chat_models import ChatOpenAI
from langchain.output_parsers import PydanticOutputParser
from typing import Type
from sklearn.cluster import KMeans
import sqlitecloud
from pinecone import Pinecone

pinecone = Pinecone()
index = pinecone.Index('books')

class ReadingPlan(BaseModel):
    timeframe: str  # Either "monthly" or "annual"
    total_books: int  # Total number of books in the plan
    unread_only: bool  # Whether the plan includes only unread books
    fav_or_input: str  # Either "fav" or "input_book", "input_author" or "input_genre"
    which: str # Either "books", "authors", "genres" or the title of the book, name of author or genre

class ExtractReadingPlanInput(Runnable):
    def __init__(self,  llm, memory = False):
        super().__init__()
        self.llm = llm
        prompt_template = PromptTemplate(
            system_template=""" 
            You are part of a book recommendation system team called Shelfmate.
            The user wants a reading plan.
            Your task is to determine whether the plan is monthly or annual, extract if the user set a maximumum number of books in the plan \
            , if the plan should exclude or not already read books and if the user wants the plan to be based on his favorites or specific input.
            'fav_or_input' value must be 'fav' if the user wants the reading plan based on favorites and 'input_book', 'input_author', 'input_genre' whether the user wants based on a specific book, author or genre. 
            The accepted values for which are 'books', 'authors', 'genres' if 'fav_or_input'='fav' and must contain the name of the book, author or genre if 'fav_or_input'='input'.
            If the user does not specify how many books he wants, set 'total_books' to 5 if 'timeframe'=='monthly' and 40 if 'timeframe'=='annual'. 
            If the user does not specify if he only wants unread books or not, set unread_only as default to True.
            You can also take into consideration the chat history between you and the user.

            Here is the user input:
            {user_input}

            Chat History:
            {chat_history}
            
            {format_instructions}
            """,
            human_template="User input: {user_input}",
        )

        self.prompt = generate_prompt_templates(prompt_template, memory=memory)
        self.output_parser = PydanticOutputParser(pydantic_object=ReadingPlan)
        self.format_instructions = self.output_parser.get_format_instructions()

        self.chain = self.prompt | self.llm | self.output_parser

    def invoke(self, inputs):
        result = self.chain.invoke(
            {
                "user_input": inputs["user_input"],
                "chat_history": inputs["chat_history"],
                "format_instructions": self.format_instructions,
            })
        return result
    
#######################################################################################################################

class ReadingPlanOutput(BaseModel):
    output: str

class CreateReadingPlanChain(Runnable):
    name: str = "CreateReadingPlanChain" 
    description: str = "Create a reading plan based on the user's favorite books, genres or authors or on a specific book, genre or author."
    args_schema: Type[BaseModel] = ReadingPlanOutput
    return_direct: bool = True

    def __init__(self, memory: bool = True):
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        self.extract_chain = ExtractReadingPlanInput(llm=self.llm)
        
        prompt_bot_return = PromptTemplate(
            system_template="""
            You are a part of the database manager team for a book recommendation platform called Shelfmate. 
            The user asked for a reading plan, for 1 month or 1 year (monthly and annual), based on their favorite genres, authors stored in a database or books \
            or based on a specific book, author or genre given in the input also stored in a database.

            Given the user input, the chat history and the list of books you **can** include in the reading plan, assess if given the timeframe is possible to include all the books in the reading plan \
            given their page numbers for an average speed reader. Moreover you have to limit the number of books in the timeframe by the maximum of {total_books} books.

            According to that, structure the calendar for the month or year taking in consideration the number of pages of each book for an average speed reader.
            You cannot suggest irrealistic number of pages in a specific timeframe. For guideline take as a maximum of 20 pages per day.
            
            Your task is to return to the user a message stating the reading plan with the suggested books, total number of pages and timeframe in a friendly way 
            and guide the user to what more they can do on the platform. That includes adding books to their read list, adding genres \
            and authors to their favorites list, receiving suggestions of books and authors.
            Do not greet the user in the beggining of the message as this is already in the middle of the conversation.

            User Input:
            {user_input}
            
            Books that can be included:
            {books_to_include}

            Number of pages per book (in the order of the books to include): 
            {book_pages}

            Time Frame: 
            {timeframe}
            
            Chat History:
            {chat_history}

            {format_instructions}
            """,
            human_template="user input: {user_input}"
        )
        
        self.prompt = generate_prompt_templates(prompt_bot_return, memory=memory)
        self.output_parser = PydanticOutputParser(pydantic_object=ReadingPlanOutput)
        self.format_instructions = self.output_parser.get_format_instructions()
        self.chain = (self.prompt | self.llm | self.output_parser).with_config({"run_name": self.__class__.__name__})
        
    def invoke(self, user_input, config):
        username = config.get('configurable').get('user_id')
        con = sqlitecloud.connect("sqlitecloud://cikwryuhhz.g6.sqlite.cloud:8860/shelfmate.db?apikey=fxZSlHTpxWU109u7go8avF2RRHsZ43JUxDfarjdFpYg")
        cursor = con.cursor()

        u_input = self.extract_chain.invoke(user_input)
        
        chain_fav = SuggestBooksGivenFavChain(return_titles=True, total_books=u_input.total_books)
        chain_input = SuggestBooksGivenInputChain(return_titles=True, total_books=u_input.total_books)
        
        if u_input.fav_or_input == 'fav': 
            self.books_to_include = chain_fav.invoke(user_input, config= config)

        else: 
            self.books_to_include = chain_input.invoke(user_input, config= config)

        self.total_books = u_input.total_books
        self.timeframe = u_input.timeframe
        self.books_to_include = [tup[0] for tup in self.books_to_include]
        
        self.book_pages = None
        # Retrieve the number of pages for each book based on titles in self.books_to_include
        if self.books_to_include:
            query = """
                SELECT page_number 
                FROM books 
                WHERE title IN ({})
            """.format(','.join('?' for _ in self.books_to_include))
            cursor.execute(query, self.books_to_include)
            results = cursor.fetchall()

            # Create a list of tuples [(title, page_number)]
            self.book_pages = [row[0] for row in results]

        # Close connection if no conditions match
        con.close()

        response = self.chain.invoke({
            "user_input": user_input['user_input'],
            'chat_history': user_input['chat_history'],
            'timeframe': self.timeframe, 
            "books_to_include": self.books_to_include,
            "total_books": self.total_books,
            "book_pages": self.book_pages,
            "format_instructions": self.format_instructions
        })
        return response.output