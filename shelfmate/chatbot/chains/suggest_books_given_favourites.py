from chatbot.chains.base import PromptTemplate, generate_prompt_templates 
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

def semantic_search(ids, k):
   
    # Generate embeddings
    desc_ids = ['desc_' + str(i) for i in ids]
    fetch_results = index.fetch(desc_ids)
    embeddings = [fetch_results.vectors[i].values for i in desc_ids]

    # Cluster embeddings
    kmeans = KMeans(n_clusters=1, random_state=42)
    kmeans.fit(embeddings)
    cluster_centers = kmeans.cluster_centers_
    
    filter_condition = {"book_id": {"$nin": ids}, 
                        "type": {"$eq": 'description'}}

    # Perform semantic search
    search_results = index.query(
        vector=cluster_centers[0].tolist(),
        top_k=k,
        include_metadata=True,
        filter=filter_condition
    )

    # Display results
    results = []
    for match in search_results["matches"]:
        results.append(
            int(match['metadata']['book_id'])
        )

    return results


class WhichFavourite(BaseModel):
    which_fav: str


class ExtractFavourite(Runnable):
    def __init__(self, llm, memory= False):
        super().__init__()

        self.llm = llm

        prompt_template = PromptTemplate(
            system_template=""" 
            You are a part of a book recomendation system team. 
            The user will ask for book sugestions. Your task is to identify if the user wants a suggestion based on their favorite books, authors or genres.
            Return the word 'books', 'authors' or 'genres' based on the user input.
            You can also take into consideration the chat history between you and the user.

            Here is the user input:
            {user_input}

            Chat History:
            {chat_history}

            {format_instructions}
            """,
            human_template="user input: {user_input}",
        )

        self.prompt = generate_prompt_templates(prompt_template, memory=memory)
        self.output_parser = PydanticOutputParser(pydantic_object=WhichFavourite)
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

class SuggestNewBooksOutput(BaseModel):
    output: str

class SuggestBooksGivenFavChain(Runnable):
    name: str = "SuggestNewBooksGivenFavoritesChain" 
    description: str = "Suggest new books based on the user's favorite books, genres, and authors."
    args_schema: Type[BaseModel] = SuggestNewBooksOutput
    return_direct: bool = True

    def __init__(self, return_titles: bool = False, total_books: int= 5, memory: bool = True):
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        self.extract_chain = ExtractFavourite(self.llm)
        self.return_titles = return_titles
        self.total_books = total_books
        self.suggestions = None
        prompt_bot_return = PromptTemplate(
            system_template="""
            You are a part of the database manager team for a book recommendation platform called Shelfmate. 
            The user asked for book suggestions based on their favorite genres, authors or books stored in a database.

            Given the user input, the chat history and the suggestions generated, your task is to return to the user a message stating the suggestions in a friendly way \
            and guide the user to what more they can do on the platform. That includes adding books to their read list, adding genres \
            and authors to their favorites list, receiving suggestions of books and authors, and creating a reading plan.
            Do not greet the user in the beggining of the message as this is already in the middle of the conversation.

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
        self.output_parser = PydanticOutputParser(pydantic_object=SuggestNewBooksOutput)
        self.format_instructions = self.output_parser.get_format_instructions()
        self.chain = (self.prompt | self.llm | self.output_parser).with_config({"run_name": self.__class__.__name__})
        
    def invoke(self, user_input, config):
        username = config.get('configurable').get('user_id')
        con = sqlitecloud.connect("sqlitecloud://cikwryuhhz.g6.sqlite.cloud:8860/shelfmate.db?apikey=fxZSlHTpxWU109u7go8avF2RRHsZ43JUxDfarjdFpYg")
        cursor = con.cursor()
        
        u_input = self.extract_chain.invoke(user_input)
        

        # Suggest books similar to user's favorite books
        if u_input.which_fav == 'books':
            # Check if the user has any books in their read list with a rating >= 4
            cursor = con.cursor()
            cursor.execute("""
                SELECT b.book_id, b.title 
                FROM read_list rl
                INNER JOIN books b ON rl.book_id = b.book_id
                WHERE rl.username = ? AND b.rating >= 4
            """, (username,))
            favorite_books = cursor.fetchall()

            if not favorite_books:
                con.close()
                return "You don't have any books with a rating higher or equal than 4 in your read list. Add some of your favorite books first so we can provide suggestions!"

            # Get list of book IDs in the user's read list
            book_ids = [book[0] for book in favorite_books]

            # Perform semantic search to find similar books
            similar_books = semantic_search(book_ids, 10)

            # Filter out books already in the user's read list and ensure rating > 4
            if similar_books:
                filtered_books = [
                    book_id for book_id in similar_books
                    if book_id not in read_list_ids
                ]

                if filtered_books:
                    query = """
                        SELECT 
                            b.title,
                            GROUP_CONCAT(a.author_name, ', ') AS authors
                        FROM books b
                        INNER JOIN authors_books ab ON b.book_id = ab.book_id
                        INNER JOIN authors a ON ab.author_id = a.author_id
                        WHERE b.book_id IN ({}) AND b.rating > 4
                        GROUP BY b.book_id
                        ORDER BY RANDOM()
                        LIMIT ?
                    """.format(','.join('?' for _ in filtered_books))
                    cursor = con.cursor()
                    cursor.execute(query, filtered_books + [self.total_books])
                    similar_books_info = cursor.fetchall()

                    if similar_books_info:
                        self.suggestions = similar_books_info
                        con.close()
                        

        # Suggest books in favorite genres
        if u_input.which_fav == 'genres':
            cursor = con.cursor()
            cursor.execute("""
                SELECT g.genre_id, g.genre 
                FROM fav_genres fg
                INNER JOIN genres g ON fg.genre_id = g.genre_id
                WHERE fg.username = ?
            """, (username,))
            favorite_genres = cursor.fetchall()

            if not favorite_genres:
                con.close()
                return "You don't have any genres set as favorites. Add some favorite genres first so we can provide suggestions!"

            else:
                genre_ids = [genre[0] for genre in favorite_genres]
                query = """
                    SELECT 
                        b.title,
                        GROUP_CONCAT(a.author_name, ', ') AS authors
                    FROM books b
                    INNER JOIN books_genres bg ON b.book_id = bg.book_id
                    INNER JOIN authors_books ab ON b.book_id = ab.book_id
                    INNER JOIN authors a ON ab.author_id = a.author_id
                    LEFT JOIN read_list rl ON b.book_id = rl.book_id
                    WHERE bg.genre_id IN ({}) AND rl.book_id IS NULL AND b.rating > 4
                    GROUP BY b.book_id
                    ORDER BY RANDOM()
                    LIMIT ?
                """.format(','.join(['?'] * len(genre_ids)))  
                cursor = con.cursor()
                cursor.execute(query, genre_ids + [self.total_books])  
                genre_based_books = cursor.fetchall()

                if genre_based_books:
                    con.close()
                    self.suggestions = genre_based_books

        # Suggest books by favorite authors
        if u_input.which_fav == 'authors':
            cursor = con.cursor()
            cursor.execute("""
                SELECT a.author_id, a.author_name 
                FROM fav_authors fa
                INNER JOIN authors a ON fa.author_id = a.author_id
                WHERE fa.username = ?
            """, (username,))
            favorite_authors = cursor.fetchall()

            if not favorite_authors:
                con.close()
                return "You don't have any authors set as favorites. Add some of your favorite authors first so we can provide suggestions!"
                
            else:
                author_ids = [author[0] for author in favorite_authors]
                query = """
                    SELECT 
                        b.title,
                        GROUP_CONCAT(a.author_name, ', ') AS authors
                    FROM books b
                    INNER JOIN authors_books ab ON b.book_id = ab.book_id
                    INNER JOIN authors a ON ab.author_id = a.author_id
                    LEFT JOIN read_list rl ON b.book_id = rl.book_id
                    WHERE ab.author_id IN ({}) AND rl.book_id IS NULL AND b.rating > 4
                    GROUP BY b.book_id
                    ORDER BY RANDOM()
                    LIMIT ?
                """.format(','.join('?' for _ in author_ids))
                cursor = con.cursor()
                cursor.execute(query, author_ids + [self.total_books])
                author_based_books = cursor.fetchall()

                if author_based_books:
                    con.close()
                    self.suggestions = author_based_books

        # Close connection if no conditions match
        con.close()
        if self.return_titles:
            return self.suggestions

        response = self.chain.invoke({
            "user_input": user_input['user_input'],
            'chat_history': user_input['chat_history'], 
            "suggestions": self.suggestions,
            "format_instructions": self.format_instructions
        })

        return response.output