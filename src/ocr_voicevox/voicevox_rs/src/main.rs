use std::fs;

fn main() -> Result<(), Box<dyn std::error::Error>> {
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

	//ファイルに保存
	fs::write("test.wav", &wav)?;
	println!("test.wavを保存しました({}バイト)", wav.len());
	Ok(())
}
