import streamlit as st
import sqlitecloud

# Display animated title
st.markdown(
    """
    <style>
    @keyframes bounce {
        0%, 20%, 50%, 80%, 100% {
            transform: translateY(0);
        }
        40% {
            transform: translateY(-10px);
        }
        60% {
            transform: translateY(-5px);
        }
    }
    .animated-title {
        font-size: 45px;
        font-weight: 800;
        text-align: center;
        animation: bounce 2s infinite;
    }
    </style>
    <div class="animated-title">Book List</div>
    """,
    unsafe_allow_html=True
)

st.write("In this page you can have access to the books available in our database!")
st.write("You will be able to filter the books by multiple categories to find the perfect book for you!")

# Connect to the database
con = sqlitecloud.connect("sqlitecloud://cikwryuhhz.g6.sqlite.cloud:8860/shelfmate.db?apikey=fxZSlHTpxWU109u7go8avF2RRHsZ43JUxDfarjdFpYg")
c = con.cursor()

# Query to find min and max for published date and number of pages
c.execute("SELECT MIN(published_date), MAX(published_date), MIN(page_number), MAX(page_number) FROM books")
min_pub_year, max_pub_year, min_pages, max_pages = c.fetchone()

# Create two columns: one for filters, one for book list
col1, col2 = st.columns([1, 3])  # First column smaller (1), second one bigger (3)

# Column 1: Filters
with col1:
    st.subheader("Filters")

    # Author and Title as search bars
    search_title = st.text_input("Search title", "")
    search_author = st.text_input("Search author", "")


    # Genre as a multi-select box
    genre_filter = st.multiselect(
        "Select genre(s)",
        ["Body, Mind & Spirit", "Language Arts & Disciplines", "Reference", "History", "Family & Relationships", "Fiction", "Juvenile Nonfiction", "Art", 
        "Foreign Language Study", "Travel", "Literacy Collections", "Business & Economics", "Drama", "Religion", "Juvenile Fiction", "Biography & Autobiography","Humor",
        "Political Science", "Social Science", "Literary Criticism", "Poetry", "Comics & Graphic Novels", "Music", "Antiques & Collectibles", "Computers", "Psychology", "Philosophy",
        "Nature", "Science", "Young Adult Fiction", "Education", "Self-Help","Cooking", "Architecture", "Transportation","Performing Arts", "Pets", "Photography","Sports & Recreation","Technology & Engineering",
        "Medical", "Crafts & Hobbies", "Health & Fitness", "Mathematics", "Law"]
    )

    

    # Published date slider (dynamic min and max)
    published_date_filter = st.slider(
        "Select publishing year",
        min_pub_year or 1900, max_pub_year or 2025, (min_pub_year or 2000, max_pub_year or 2025)
    )

    # Number of pages slider (dynamic min and max)
    nrpages_filter = st.slider(
        "Select number of pages",
        min_pages or 50, max_pages or 1000, (min_pages or 100, max_pages or 500)
    )

# Column 2: Books Display
with col2:
    # Base query to fetch books from the read list with filters
    query = '''
        SELECT b.title, b.published_date, b.page_number, b.description
        FROM books b 
        INNER JOIN authors_books ab on b.book_id = ab.book_id
        INNER JOIN authors a on ab.author_id = a.author_id
        INNER JOIN books_genres bg on b.book_id = bg.book_id
        INNER JOIN genres g on g.genre_id = bg.genre_id
        WHERE 1=1
    '''

    filters = []

    # Apply title search filter
    if search_title:
        query += " AND b.title LIKE ?"
        filters.append(f"%{search_title}%")
    
    # Apply author search filter
    if search_author:
        query += " AND a.author_name LIKE ?"
        filters.append(f"%{search_author}%")

    # Apply genre filter (multiple selection)
    if genre_filter:
        genre_placeholders = ', '.join(['?'] * len(genre_filter))
        query += f" AND g.genre IN ({genre_placeholders})"
        filters.extend(genre_filter)

    # Apply published year filter (slider range)
    if published_date_filter:
        query += " AND b.published_date BETWEEN ? AND ?"
        filters.extend(published_date_filter)

    # Apply number of pages filter (slider range)
    if nrpages_filter:
        query += " AND b.page_number BETWEEN ? AND ?"
        filters.extend(nrpages_filter)

    # Add random selection and limit to 20 results
    query += " ORDER BY b.title LIMIT 20"

    
    filters = [item for item in filters if not isinstance(item, tuple)]
    # Execute the query with filters
    c = con.cursor()
    c.execute(query, filters)
    book_list = c.fetchall()
    

    # Display the filtered books
    if book_list:
        for book in book_list:
            title, published_date, pages, description = book

            st.markdown(f"""
            <div style="border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 10px;">
                <h4>{title}</h4>
                <p><b>Published Year:</b> {published_date}</p>
                <p><b>Pages:</b> {pages}</p>
                <p><b>Description:</b> {description}</p>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.write("No books found matching the selected filters.")