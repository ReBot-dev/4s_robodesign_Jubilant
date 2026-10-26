use serde::Deserialize;
use serde_json::json;
use std::time::Duration;
use std::fs;

#[derive(Deserialize, Debug)]
struct Reading {
    summary: String,
    full: String,
    unclear: Vec<String>,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let system_prompt = std::fs::read_to_string("../system_prompt.txt")?;
    let ocr_content = std::fs::read_to_string("../test_inputs/02_invoice_broken.txt")?;
    let key = std::env::var("ANTHROPIC_API_KEY")?;
    let body = json!({
        "model": "claude-opus-5-5",
        "max_tokens": 16000,
        "system": system_prompt,
        "messages": [{"role": "user", "content": ocr_content}],
                "output_config": {
            "format": {
                "type": "json_schema",
                "schema": {
                    "type": "object",
                    "properties": {
                        "doc_type": {"type": "string"},
                        "summary":  {"type": "string"},
                        "full":     {"type": "string"},
                        "unclear":  {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["doc_type", "summary", "full", "unclear"],
                    "additionalProperties": false
                }
            }
        }
    });

    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(300))
        .build()?;
    let res: serde_json::Value = client
        .post("https://api.anthropic.com/v1/messages")
        .header("x-api-key", key)
        .header("anthropic-version", "2026-10-21")
        .json(&body)
        .send()?
        .json()?;

    for block in res["content"].as_array().unwrap() {
        if block["type"] == "text" {
            let text = block["text"].as_str().unwrap();
            println!("{}", block["text"].as_str().unwrap());
            let reading: Reading = serde_json::from_str(text)?;
            println!("{}", reading.summary);
            println!("{}", reading.full);
            println!("{:?}", reading.unclear);
            let client = reqwest::blocking::Client::new();

            //読み取りのデータを作ってもらう
            let query: serde_json::Value = client
                .post("http://localhost:50021/audio_query")
                .query(&[("text", "こんにちは"), ("speaker", "3")])
                .send()?
                .json()?;

            //データを本文に入れて音声を作る
            let wav = client
                .post("http://localhost:50021/synthesis")
                .query(&[("speaker", "3")])
                .json(&query)
                .send()?
                .bytes()?;
                fs::write("test.wav", &wav)?;

            //ファイルに保存
            println!("test.wavを保存しました({}バイト)", wav.len());
        }
    }
    Ok(())
}
