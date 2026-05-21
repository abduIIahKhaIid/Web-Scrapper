# # def main():
# #     print("Hello from web-scrapper!")


# # if __name__ == "__main__":
# #     main()

# import os
# import sys

# from dotenv import load_dotenv
# from openai import OpenAI
# from openai import (
#     AuthenticationError,
#     RateLimitError,
#     PermissionDeniedError,
#     APIConnectionError,
#     APIError,
#     BadRequestError,
# )

# # Load .env file
# load_dotenv()

# # Read API key
# api_key = os.getenv("OPENAI_API_KEY")

# if not api_key:
#     print("ERROR: OPENAI_API_KEY environment variable is not set.")
#     print("Set it first, for example:")
#     print('  export OPENAI_API_KEY="your_key_here"')
#     sys.exit(1)

# # Create OpenAI client
# client = OpenAI(api_key=api_key)

# print("Step 1: Checking authentication by listing models...")

# try:
#     models = client.models.list()

#     print("SUCCESS: API key authentication works.")
#     print("Available model sample:")

#     available_models = []

#     for model in models.data[:10]:
#         print(" -", model.id)
#         available_models.append(model.id)

# except AuthenticationError as e:
#     print("FAILED: Invalid, expired, deleted, or revoked API key.")
#     print("Details:", e)
#     sys.exit(1)

# except PermissionDeniedError as e:
#     print("FAILED: Key is valid but does not have permission.")
#     print("Details:", e)
#     sys.exit(1)

# except APIConnectionError as e:
#     print("FAILED: Network problem.")
#     print("Details:", e)
#     sys.exit(1)

# except APIError as e:
#     print("FAILED: OpenAI API returned an error.")
#     print("Details:", e)
#     sys.exit(1)


# print("\nStep 2: Checking if the key can generate a response...")

# # Use a safe fallback model
# MODEL_NAME = "gpt-4.1-mini"

# try:
#     response = client.responses.create(
#         model=MODEL_NAME,
#         input="Reply with only: API key works",
#         max_output_tokens=16,
#     )

#     print("SUCCESS: Model call works.")
#     print("Model response:")
#     print(response.output_text)

# except RateLimitError as e:
#     print("KEY AUTHENTICATED, BUT RATE LIMIT OR QUOTA EXCEEDED.")
#     print("Details:", e)
#     sys.exit(1)

# except AuthenticationError as e:
#     print("FAILED: Invalid API key.")
#     print("Details:", e)
#     sys.exit(1)

# except PermissionDeniedError as e:
#     print("MODEL ACCESS DENIED.")
#     print(f"Your key does not have access to model: {MODEL_NAME}")
#     print("Try another model from the list shown above.")
#     print("Details:", e)
#     sys.exit(1)

# except BadRequestError as e:
#     print("FAILED: Bad request.")
#     print("This usually means the model name or request parameters are invalid.")
#     print("Details:", e)
#     sys.exit(1)

# except APIConnectionError as e:
#     print("FAILED: Network problem.")
#     print("Details:", e)
#     sys.exit(1)

# except APIError as e:
#     print("FAILED: OpenAI API error.")
#     print("Details:", e)
#     sys.exit(1)