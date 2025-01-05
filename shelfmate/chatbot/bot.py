# Import necessary classes and modules for chatbot functionality
from typing import Callable, Dict, Optional

from chatbot.memory import MemoryManager

from chatbot.chains.is_prompt_injection import IsPromptInjection

from chatbot.chains.update_profile_info import UpdateUserInfoChain
from chatbot.chains.insert_fav_author_genre import AddFavAuthorGenreChain
from chatbot.chains.add_book_read_list import AddBookReadListChain
from chatbot.chains.router import RouterChain
from chatbot.router.loader import load_intention_classifier
from chatbot.chains.chitchat import ChitChatResponseChain, ChitChatClassifierChain
from chatbot.chains.suggest_books import ExtractInput_Books
from chatbot.chains.suggest_authors import ExtractInput_Authors
from chatbot.chains.suggest_books_given_trope import SuggestBookGivenTropeChain
from chatbot.chains.browser import BrowserChain
from chatbot.chains.readingplan import CreateReadingPlanChain
from chatbot.rag.rag import RagChain

from langchain_core.runnables.history import RunnableWithMessageHistory


class MainChatbot:
    """A bot that handles customer service interactions by processing user inputs and
    routing them through configured reasoning and response chains.
    """

    def __init__(self):
        """Initialize the bot with session and language model configurations."""
        # Initialize the memory manager to manage session history
        self.memory = MemoryManager()

        # Map intent names to their corresponding reasoning and response chains
        self.chain_map = {
            "update_profile_info": self.add_memory_to_runnable(UpdateUserInfoChain()),
            "insert_new_favorite_author_genre": self.add_memory_to_runnable(AddFavAuthorGenreChain()),
            "add_book_to_read_list": self.add_memory_to_runnable(AddBookReadListChain()),
            "router": RouterChain(),
            "chitchat": self.add_memory_to_runnable(ChitChatResponseChain()),
            "chitchat_class": ChitChatClassifierChain(),
            "suggest_books": self.add_memory_to_runnable(ExtractInput_Books()),
            "suggest_authors": self.add_memory_to_runnable(ExtractInput_Authors()),
            "suggest_books_given_trope": self.add_memory_to_runnable(SuggestBookGivenTropeChain()),
            "browse_available_genres_books_authors": self.add_memory_to_runnable(BrowserChain()),
            "create_reading_plan": self.add_memory_to_runnable(CreateReadingPlanChain())
        }
        

        # Map of intentions to their corresponding handlers
        self.intent_handlers: Dict[Optional[str], Callable[[Dict[str, str]], str]] = {
            "update_profile_info": self.handle_update_profile_info,
            "insert_new_favorite_author_genre": self.handle_new_favorite_author_genre,
            "add_book_to_read_list": self.handle_add_book_to_read_list,
            "chitchat": self.handle_chitchat_intent,
            "suggest_books": self.handle_suggest_books,
            "suggest_authors": self.handle_suggest_authors,
            "suggest_books_given_trope": self.handle_suggest_books_given_trope,
            "recommend_bookstores_per_district": self.handle_rag,
            "ask_about_chatbot_features": self.handle_rag,
            "ask_about_company_info": self.handle_rag,
            "browse_available_genres_books_authors": self.handle_browser,
            "create_reading_plan": self.handle_create_reading_plan,
        }

        # Load the intention classifier to determine user intents
        self.intention_classifier = load_intention_classifier()

    def user_login(self, username: str, conversation_id: str) -> None:
        """Log in a user by setting the user and conversation identifiers.

        Args:
            username: Identifier for the user.
            conversation_id: Identifier for the conversation.
        """
        self.username = username
        self.conversation_id = conversation_id
        self.memory_config = {
            "configurable": {
                "conversation_id": self.conversation_id,
                "user_id": self.username,
            }
        }

    def add_memory_to_runnable(self, original_runnable):
        """Wrap a runnable with session history functionality.

        Args:
            original_runnable: The runnable instance to which session history will be added.

        Returns:
            An instance of RunnableWithMessageHistory that incorporates session history.
        """
        return RunnableWithMessageHistory(
            original_runnable,
            self.memory.get_session_history,  # Retrieve session history
            input_messages_key="user_input",  # Key for user inputs
            history_messages_key="chat_history",  # Key for chat history
            history_factory_config=self.memory.get_history_factory_config(),  # Config for history factory
        ).with_config(
            {
                "run_name": original_runnable.__class__.__name__
            }  # Add runnable name for tracking
        )

    def get_chain(self, intent: str):
        """Retrieve the reasoning and response chains based on user intent.

        Args:
            intent: The identified intent of the user input.

        Returns:
            A tuple containing the reasoning and response chain instances for the intent.
        """
        return self.chain_map[intent]


    def get_user_intent(self, user_input: Dict):
        """Classify the user intent based on the input text.

        Args:
            user_input: The input text from the user.

        Returns:
            The classified intent of the user input.
        """
        # Retrieve possible routes for the user's input using the classifier
        intent_routes = self.intention_classifier.retrieve_multiple_routes(
            user_input["user_input"]
        )

        # Handle cases where no intent is identified
        if len(intent_routes) == 0:
            return None
        else:
            intention = intent_routes[0].name  # Use the first matched intent

        # Validate the retrieved intention and handle unexpected types
        if intention is None:
            return None
        elif isinstance(intention, str):
            return intention
        else:
            # Log the intention type for unexpected cases
            intention_type = type(intention).__name__
            print(
                f"I'm sorry, I didn't understand that. The intention type is {intention_type}."
            )
            return None

    def handle_update_profile_info(self, user_input: Dict[str, str]) -> str:
        """Handle the update profile info intent by processing user input and providing a response.

        Args:
            user_input: The input text from the user.

        Returns:
            The content of the response after processing through the chains.
        """
        # Retrieve reasoning and response chains for the update profile info intent
        chain = self.get_chain("update_profile_info")
        user_input['chat_history'] = self.memory.get_session_history(
            self.username, self.conversation_id
        )
        # Generate a response using the output of the reasoning chain
        response = chain.invoke(user_input, config=self.memory_config)

        return response

    def handle_new_favorite_author_genre(self, user_input: Dict[str, str]) -> str:
        """Handle the insert new fav author/genre intent by processing user input and providing a response.

        Args:
            user_input: The input text from the user.

        Returns:
            The content of the response after processing through the chains.
        """
        # Retrieve reasoning and response chains for the insert new fav author/genre intent
        chain = self.get_chain("insert_new_favorite_author_genre")
        user_input['chat_history'] = self.memory.get_session_history(
            self.username, self.conversation_id
        )
        # Generate a response using the output of the reasoning chain
        response = chain.invoke(user_input, config=self.memory_config)

        return response

    def handle_add_book_to_read_list(self, user_input: Dict[str, str]) -> str:
        """Handle the add book to the read list intent by processing user input and providing a response.

        Args:
            user_input: The input text from the user.

        Returns:
            The content of the response after processing through the chains.
        """
        # Retrieve reasoning and response chains for the add book to read list intent
        chain = self.get_chain("add_book_to_read_list")
        user_input['chat_history'] = self.memory.get_session_history(
            self.username, self.conversation_id
        )
        # Generate a response using the output of the reasoning chain
        response = chain.invoke(user_input, config=self.memory_config)

        return response

    def handle_suggest_books(self, user_input: Dict[str, str]) -> str:
        """Handle the suggest books intent by processing user input and providing a response.

        Args:
            user_input: The input text from the user.

        Returns:
            The content of the response after processing through the chains.
        """
        # Retrieve reasoning and response chains for the add book to read list intent
        chain = self.get_chain("suggest_books")
        user_input['chat_history'] = self.memory.get_session_history(
            self.username, self.conversation_id
        )
        # Generate a response using the output of the reasoning chain
        response = chain.invoke(user_input, config=self.memory_config)

        return response

    def handle_suggest_authors(self, user_input: Dict[str, str]) -> str:
        """Handle the suggest authors intent by processing user input and providing a response.

        Args:
            user_input: The input text from the user.

        Returns:
            The content of the response after processing through the chains.
        """
        # Retrieve reasoning and response chains for the add book to read list intent
        chain = self.get_chain("suggest_authors")
        user_input['chat_history'] = self.memory.get_session_history(
            self.username, self.conversation_id
        )
        # Generate a response using the output of the reasoning chain
        response = chain.invoke(user_input, config=self.memory_config)

        return response

    def handle_suggest_books_given_trope(self, user_input: Dict[str, str]) -> str:
        """Handle the suggest books given trope intent by processing user input and providing a response.

        Args:
            user_input: The input text from the user.

        Returns:
            The content of the response after processing through the chains.
        """
        # Retrieve reasoning and response chains for the add book to read list intent
        chain = self.get_chain("suggest_books_given_trope")
        user_input['chat_history'] = self.memory.get_session_history(
            self.username, self.conversation_id
        )
        # Generate a response using the output of the reasoning chain
        response = chain.invoke(user_input, config=self.memory_config)

        return response

    def handle_browser(self, user_input: Dict[str, str]) -> str:
        """Handle the browse available authors, books and genres intent by processing user input and providing a response.

        Args:
            user_input: The input text from the user.

        Returns:
            The content of the response after processing through the chains.
        """
        # Retrieve reasoning and response chains for the add book to read list intent
        chain = self.get_chain("browse_available_genres_books_authors")
        user_input['chat_history'] = self.memory.get_session_history(
            self.username, self.conversation_id
        )
        # Generate a response using the output of the reasoning chain
        response = chain.invoke(user_input, config=self.memory_config)

        return response

    def handle_create_reading_plan(self, user_input: Dict[str, str]) -> str:
        """Handle the create reading plan intent by processing user input and providing a response.

        Args:
            user_input: The input text from the user.

        Returns:
            The content of the response after processing through the chains.
        """
        # Retrieve reasoning and response chains for the add book to read list intent
        chain = self.get_chain("create_reading_plan")
        user_input['chat_history'] = self.memory.get_session_history(
            self.username, self.conversation_id
        )
        # Generate a response using the output of the reasoning chain
        response = chain.invoke(user_input, config=self.memory_config)

        return response

    def handle_rag(self, user_input: Dict[str, str]) -> str:
        """Handle the RAG intent by processing user input and providing a response.

        Args:
            user_input: The input text from the user.

        Returns:
            The content of the response after processing through the chains.
        """
        # Retrieve reasoning and response chains for the RAG intent
        rag = RagChain(username=self.username)
        
        # Generate a response using the output of the reasoning chain
        response = rag.run_chain(question=user_input['user_input'])

        return response

    def handle_chitchat_intent(self, user_input: Dict[str, str]) -> str:
        """Handle chitchat intents

        Args:
            user_input: The input text from the user.

        Returns:
            The content of the response after processing through the new chain.
        """
        # Retrieve reasoning and response chains for the chitchat intent
        chain = self.get_chain("chitchat")

        # Generate a response using the output of the reasoning chain
        response = chain.invoke(user_input, config=self.memory_config)

        return response

    def handle_unknown_intent(self, user_input: Dict[str, str]) -> str:
        """Handle unknown intents by providing a chitchat response.

        Args:
            user_input: The input text from the user.

        Returns:
            The content of the response after processing through the new chain.
        """

        chitchat_reasoning_chain = self.get_chain("chitchat_class")
        
        input_message = {}

        input_message["user_input"] = user_input["user_input"]
        input_message["chat_history"] = self.memory.get_session_history(
            self.username, self.conversation_id
        )
        
        reasoning_output = chitchat_reasoning_chain.invoke(input_message)
        
        if reasoning_output.chitchat:
            return self.handle_chitchat_intent(user_input)
        else:
            router_reasoning_chain2 = self.get_chain("router")
            reasoning_output2 = router_reasoning_chain2.invoke(input_message)
            new_intention = reasoning_output2.intent
            new_handler = self.intent_handlers.get(new_intention)
            return new_handler(user_input)



    def save_memory(self) -> None:
        """Save the current memory state of the bot."""
        self.memory.save_session_history(self.username, self.conversation_id)

    def process_user_input(self, user_input: Dict[str, str]) -> str:
        """Process user input by routing through the appropriate intention pipeline.

        Args:
            user_input: The input text from the user.

        Returns:
            The content of the response after processing through the chains.
        """
        # Detect if there are dangers of prompt injection in the user input
        prompt_injection_chain = IsPromptInjection()
        result = prompt_injection_chain.invoke(user_input).is_prompt_injection

        if not result:
            # Classify the user's intent based on their input
            intention = self.get_user_intent(user_input)

            # Route the input based on the identified intention
            handler = self.intent_handlers.get(intention, self.handle_unknown_intent)
            return handler(user_input)
        else:
            return "It was detected prompt injection risks or malicious content in your input."
