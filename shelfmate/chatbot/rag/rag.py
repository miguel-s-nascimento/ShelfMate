# Standard Library Imports
import os
from typing import List

# Third-Party Libraries
from pinecone import Index, Pinecone

# LangChain Libraries
from langchain_openai import OpenAIEmbeddings
from langchain_community.chat_models import ChatOpenAI
from langchain_pinecone import PineconeVectorStore
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

from chatbot.chains.base import PromptTemplate, generate_prompt_templates
import sqlitecloud

class RagChain:

    def __init__(self, username):
        
        def format_docs(documents):
            return "\n\n".join(doc.page_content for doc in documents)
        
        pc = Pinecone()
        index: Index = pc.Index("documents")
        vector_store = PineconeVectorStore(index=index, embedding=OpenAIEmbeddings(model="text-embedding-ada-002"))
        retriever = vector_store.as_retriever(
            search_type="similarity_score_threshold",
            search_kwargs={"k": 2, "score_threshold": 0.5})
        
        self.llm = ChatOpenAI(model='gpt-4o-mini', temperature=0.2)

        con = sqlitecloud.connect("sqlitecloud://cikwryuhhz.g6.sqlite.cloud:8860/shelfmate.db?apikey=fxZSlHTpxWU109u7go8avF2RRHsZ43JUxDfarjdFpYg")
        cursor = con.cursor()
        user_district = cursor.execute(f"SELECT district FROM users WHERE username = ?", (username,)).fetchone()[0]

        self.template = PromptTemplate(system_template=f"""You are the Shelfmate chatbot, an online platform that focus on book recommendations. 
                Your task is to clarify the features of the book recommendation system and other Shelfmate features, answer questions \
                about the ShelfMate Company, or provide the best bookstores for a specific district.
                Use the following pieces of context to answer the user question at the end.
                Use three sentences maximum and keep the answer as concise as possible.                            
                If the user asks for bookstores in their district or in the district they live in, use this district: {user_district}.
                Do not greet the user in the beggining of the message as this is already in the middle of the conversation."""
        +
        """
        
        Use this context to answer the user question:
        {context}

        Question: {question}
        """, human_template="Question: {question}")

        self.custom_rag_prompt = generate_prompt_templates(self.template, memory=False)

        self.rag_chain = (
            {"context": retriever | format_docs, 
            "question": RunnablePassthrough()
            }
            | self.custom_rag_prompt
            | self.llm
            | StrOutputParser()
        )

    def run_chain(self, question) -> str:
        return self.rag_chain.invoke(question)