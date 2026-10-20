from pydantic import BaseModel

class Reading(BaseModel):
	doc_type: str
	summary: str
	full: str
	unclear: list[str]

import os
here = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(here, "test_inputs", "02_invoice_broken.txt")
prompt = os.path.join(here, "system_prompt.txt")
with open(path,encoding="utf-8") as f:
        ocr_text = f.read()
with open(prompt,encoding="utf-8") as p:
	system_prompt = p.read()

import anthropic
client = anthropic.Anthropic()

response = client.messages.parse(
        model="claude-opus-5-5",
        max_tokens=16000,
        system=system_prompt,
        messages=[{"role": "user", "content": ocr_text}],
	output_format = Reading
)
reading = response.parsed_output

print(reading.summary)

print(reading.full)

print(reading.unclear)
