import streamlit as st
import requests
import json 
from openai import OpenAI
from pprint import pprint
import pandas as pd

model = "gpt-4o-mini"

JUDILIBRE_AUTH_URL = "https://oauth.piste.gouv.fr/api/oauth/token HTTP/1.1"
JUDILIBRE_QUERY_URL = "https://api.piste.gouv.fr/cassation/judilibre/v1.0/search"
# Transform the client info into secret variables !



# Show title and description.
st.title("💬 Chatbot")
st.write(
    f"This is a simple chatbot that uses OpenAI's model {model} to generate responses. "
    "To use this app, you need to provide an OpenAI API key, which you can get [here](https://platform.openai.com/account/api-keys). "
    "You can also learn how to build this app step by step by [following our tutorial](https://docs.streamlit.io/develop/tutorials/llms/build-conversational-apps)."
)

oauth_data = {
    "grant_type": "client_credentials",
    "scope": "openid",
    "client_id": st.secrets["PISTE_CLIENT_ID"],
    "client_secret": st.secrets["PISTE_CLIENT_SECRET"],
    }
# ideally, request token only if no token or previous token is outdated
auth_request = requests.post(JUDILIBRE_AUTH_URL, data=oauth_data)
#print(auth_request.json())
token = auth_request.json()["access_token"]

api_prompt = """Voici une question d'un utilisateur concernant la jurisprudence en France:
:USER_REQUEST:
Extrait le ou les mots clés nécessaire à la requête de l'API Judilibre. Soit le plus synthétique dans les mots clés et essaie de minimiser le nombre de mots.
Ecris la requête sous forme des mots les plus impactans, sans mots de liaison aucun."""
api_functions =  [
    {
      "type": "function",
      "function": {
          "name": 'get_user_query',
          "description": "Récupère le ou les mots-clés à envoyer à l'API Judilibre",
          "parameters": {
            "type": 'object',
            "properties": {
            "query": {
              "type":'string',
              "description":"Variable indiquant le ou les mots-clés à envoyer à l'API Judilibre."
              }
          },
          'required': [
            "query"
          ],
        }
      },
    },
]

# Ask user for their OpenAI API key via `st.text_input`.
# Alternatively, you can store the API key in `./.streamlit/secrets.toml` and access it
# via `st.secrets`, see https://docs.streamlit.io/develop/concepts/connections/secrets-management
openai_api_key = st.secrets["OPENAI_API_KEY"]
if not openai_api_key:
    st.info("Please add your OpenAI API key to continue.", icon="🗝️")
else:

    # Create an OpenAI client.
    client = OpenAI(api_key=openai_api_key)

    # Create a session state variable to store the chat messages. This ensures that the
    # messages persist across reruns.
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display the existing chat messages via `st.chat_message`.
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Create a chat input field to allow the user to enter a message. This will display
    # automatically at the bottom of the page.
    answer_dict = {}
    if prompt := st.chat_input("What is up?"):

        # Store and display the current prompt.
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        api_messages = [{"role": "user", "content": api_prompt.replace(":USER_REQUEST:",prompt)}]
        completion = client.chat.completions.create(
        model=model,
        messages= api_messages,
        temperature=0,
        tools=api_functions,
        tool_choice="required" if api_functions is not None else "none"
        )
        result = json.loads(completion.model_dump_json())
        function_answers = result["choices"][0]["message"]["tool_calls"]
        for function_result in function_answers:
            function_dict = json.loads(function_result["function"]["arguments"])
        query = function_dict["query"]

        # Then send the query
        headers = {"Authorization": f"Bearer {token}"}
        params = {"query": query, "page_size":50,"sort":"score","page":0}
        query_request = requests.get(JUDILIBRE_QUERY_URL, headers=headers, params=params)
        # Les résultats sont paginés, idéalement il faudrait tout récupérer
        results_summaries = []
        print(query)
       
        while query_request.json()["next_page"]:
            print(f"page {query_request.json()['page']}")
            results = query_request.json()["results"]
            for result_id, result in enumerate(results):
                pprint(result["number"] +": "+result["summary"])
                if "summary" in result:
                    results_summaries.append({"result_id": result_id, "summary": result["number"] +": "+ result["summary"]})
                else:
                    results_summaries.append({"result_id": result_id, "summary":  result["number"] +": "+ result["highlights"]["text"][0]})
            params["page"] += 1
            query_request = requests.get(JUDILIBRE_QUERY_URL, headers=headers, params=params)
            print("next page")
            break

        # Generate a response using the OpenAI API.
        stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user","content":f"Tu es un robot avocat. Voici une question d'un client:\n'{prompt}'\nVoici une liste de documents:\n" +"\n".join([r["summary"] for r in results_summaries]) +"\n . Utilise ces documents pour répondre le plus précisément possible à la question du client. Cite les extraits de documents qui sont pertinents."}],
            stream=True,
            temperature=0
        )
        # Stream the response to the chat using `st.write_stream`, then store it in 
        # session state.
        with st.chat_message("assistant"):
            response = st.write_stream(stream)
        st.session_state.messages.append({"role": "assistant", "content": response})
