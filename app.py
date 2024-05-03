import os
import streamlit as st
from openai import OpenAI
from pathlib import Path

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.set_page_config(page_title="BookRook", page_icon="♖")
st.title("BookRook: Chess Instructor")
st.write("Upload a chess book/pdf to start learning!")


# Function to accept a file from the user to add to knowledge base
def upload_user_file():
    user_file = st.file_uploader("Choose a file", type=None)
    if user_file:
        save_folder = './.streamlit/uploads'
        save_path = Path(save_folder, user_file.name)
        if save_path.exists():
            st.success(f'File {user_file.name} has already been saved before!')
        else:
            with open(save_path, mode='wb') as f:
                f.write(user_file.getvalue())
            st.success(f'File {user_file.name} is successfully saved!')

        # You can now access the saved PDF file using its path
        st.write("You can access the uploaded PDF file at the following path:")
        st.write(os.path.join("uploads", user_file.name))

        return user_file.name
    else:
        st.info(f'No file has been uploaded. Please upload a file! by upload_user_file')
        st.stop()


# Run function
filename = upload_user_file()


# Create a vector store called "Chess Materials"
def create_vectorstore():
    vector_store = client.beta.vector_stores.create(name="Chess Materials")
    return vector_store


# Upload initial knowledge base files to OpenAI
def upload_base_files():
    file_paths = ["sample_chess_1.pdf"]
    files = [open(path, "rb") for path in file_paths]
    return files


# Use the upload and poll SDK helper to add files to the vector store, and poll the status of completion.
def populate_vectorstore(vector_store_id, files):
    batch = client.beta.vector_stores.file_batches.upload_and_poll(
        vector_store_id=vector_store_id, files=files
    )
    return batch


# Create the initial setup settings for the "Chess Master Assistant"
def create_assistant(vector_store_id):
    assistant = client.beta.assistants.create(
        name="Chess Master Assistant",
        instructions=f"""
        You are an expert chess master. Use your knowledge base to answer questions about chess.
        Employ chess notations and memorization techniques when responding to user queries.
        Also you can play a game of chess using chess notations.
        Use files in the {vector_store_id} to respond to chess moves played by the User.
        """,
        model="gpt-3.5-turbo",
        tools=[{"type": "file_search"}],
        tool_resources={"file_search": {"vector_store_ids": [vector_store_id]}}
    )
    return assistant


# Upload the user provided file to OpenAI
def update_base_files(new_file):
    save_folder = './.streamlit/uploads'
    save_path = Path(save_folder, new_file)
    if save_path.exists():
        file_message = client.files.create(
            file=open(f"{save_path}", "rb"), purpose="assistants"
        )
        return file_message
    else:
        st.warning(f'No file has been uploaded. Please upload a file! by update_base_files')


# Create a thread and attach the file to the message
def create_thread(message_file_id, content):
    message_thread = client.beta.threads.create(
        messages=[
            {
                "role": "user",
                "content": content,
                # Attach the new file to the message.
                "attachments": [
                    {"file_id": message_file_id, "tools": [{"type": "file_search"}]}
                ],
            }
        ]
    )
    return message_thread


# Use the create and poll SDK helper to create a run and poll the status of
# the run until it's in a terminal state.
def run_message(thread_id, assistant_id):
    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread_id, assistant_id=assistant_id
    )

    messages = list(client.beta.threads.messages.list(thread_id=thread_id, run_id=run.id))
    return messages


# Display response from the assistant
def process_response(messages):
    message_content = messages[0].content[0].text
    annotations = message_content.annotations
    citations = []
    for index, annotation in enumerate(annotations):
        message_content.value = message_content.value.replace(annotation.text, f"[{index}]")
        if file_citation := getattr(annotation, "file_citation", None):
            cited_file = client.files.retrieve(file_citation.file_id)
            citations.append(f"[{index}] {cited_file.filename}")

    return message_content.value, citations


with st.spinner('Creating vectorstore...'):
    vectorstore = create_vectorstore()
    st.success("Vectorstore created successfully!")
with st.spinner('Uploading base files...'):
    file_streams = upload_base_files()
    st.success("Base files uploaded successfully!")
with st.spinner('Populating vectorstore...'):
    file_batch = populate_vectorstore(vector_store_id=vectorstore.id, files=file_streams)
    st.success("Vectorstore populated successfully!")
with st.spinner('Creating assistant...'):
    chess_assistant = create_assistant(vector_store_id=vectorstore.id)
    st.success("Assistant created successfully!")
with st.spinner('Updating base files...'):
    message_file = update_base_files(new_file=filename)
    st.success("Base file updated successfully!")


# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Accept user input
if user_query := st.chat_input("How can I help you master chess?"):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": user_query})

    # Display user message in chat message container
    with st.chat_message("user"):
        st.markdown(user_query)

    with st.chat_message("assistant"):
        # Run functions

        with st.spinner('Generating response...'):
            message_placeholder = st.empty()

            with st.spinner('Creating message threads...'):
                thread = create_thread(message_file_id=message_file.id, content=user_query)
                st.success("Message thread created successfully!")
            with st.spinner('Running message threads...'):
                assistant_messages = run_message(thread_id=thread.id, assistant_id=chess_assistant.id)
                st.success("Message thread run successfully!")

            response_and_citation = process_response(messages=assistant_messages)
            # Save the assistant responses
            response = response_and_citation[0]
            citation = response_and_citation[1]

            # print(message_content.value)
            # print("\n".join(citations))
            message_placeholder.markdown(response)
    st.session_state.messages.append({"role": "assistant", "content": response})
