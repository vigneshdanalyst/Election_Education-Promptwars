# VoteWise India 🇮🇳

VoteWise India is a comprehensive, production-grade Election Process Education Assistant for India. It provides real-time information about the Indian electoral process, candidate details, live results, and an AI-powered chat assistant.

## Features

*   **🗓️ Timeline**: Interactive visual timeline of the 7 phases of Indian elections.
*   **🔍 Candidate Lookup**: Search for candidate affidavits, including assets and criminal records.
*   **📊 Live Results**: Real-time election results with maps and charts.
*   **🗳️ Voter Info**: Locate polling booths and check registration details.
*   **🤖 AI Chat**: Ask election-related questions using Groq or local Ollama.
*   **📰 Updates**: Latest press releases from the Election Commission of India.

## Tech Stack

*   **Frontend**: Vanilla HTML + CSS + JS (Single Page Application)
*   **Backend**: Python FastAPI
*   **Database**: SQLite
*   **Scraping**: BeautifulSoup4, HTTPX
*   **AI**: Groq API / local Ollama (gemma2:2b)

## Setup and Running Locally

1.  **Clone the repository**:
    ```bash
    git clone <repository_url>
    cd Election_Education-Promptwars
    ```

2.  **Install requirements**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Environment Variables**:
    *   Copy `.env.example` to `.env`.
    *   (Optional) Add your Groq API key to `.env` for the cloud-based LLM. If omitted, it will try to use a local Ollama instance running on port 11434.

4.  **Run the backend**:
    ```bash
    uvicorn main:app --reload --port 8080
    ```

5.  **Access the application**:
    Open your browser and navigate to `http://localhost:8080`.

## Deployment to GCP (Cloud Run)

The application is configured to be deployed on Google Cloud Run using the free tier.

1.  **Ensure you have the Google Cloud SDK installed and authenticated.**
2.  **Submit the build to Cloud Build**:
    ```bash
    gcloud builds submit --config cloudbuild.yaml
    ```
    Ensure the Cloud Build service account has the necessary permissions to deploy to Cloud Run.
