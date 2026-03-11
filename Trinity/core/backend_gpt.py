import openai
import os

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY


class GPTBackend:
    def __init__(self, model="gpt-4o-mini"):
        self.model = model

    def generate_stream(self, messages, max_completion_tokens=512):
       
        try:
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=messages,
                max_tokens=max_completion_tokens,
                temperature=0.7,
                stream=True,
            )

            for chunk in response:
                if (
                    "choices" in chunk
                    and len(chunk["choices"]) > 0
                    and "delta" in chunk["choices"][0]
                ):
                    delta = chunk["choices"][0]["delta"]
                    if "content" in delta:
                        yield delta["content"]

        except Exception as e:
            yield f"[ERRO] {str(e)}"

    def generate_full_response(self, messages, max_completion_tokens=512):
        
        try:
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=messages,
                max_tokens=max_completion_tokens,
                temperature=0.7,
                stream=False,
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"[ERRO] {str(e)}"

    def summarize(self, text):
      
        messages = [
            {"role": "system", "content": "Resuma o texto a seguir em tópicos claros e diretos."},
            {"role": "user", "content": text}
        ]
        result = ""
        for chunk in self.generate_stream(messages, max_completion_tokens=512):
            result += chunk
        return result
