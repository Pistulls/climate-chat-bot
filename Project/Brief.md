
### Brief

For this project we will be writing python to do the following:

* Use embedding to store the source docs in to a vector database
* Use an LLM via OpenRouter to take a context based on the incoming question whereby the context is constructed using the vector database embeddings to fetch related information to answer the question. The responding statement will aim to provide key arguments against a view point on climate change related topics such as "The sun doesn't shine at night so solar is pointless" could return various evidence to counter this such as battery price and adoption, the amount of power being produced by solar in 2026 etc. These question and responses will be stored in a database which provides a cache of known responses, this will be the "ResponseCache". This will also need to be a vector based db to allow for searching for near matches to variations on the same question.
* When an initial question comes in, it will first check the ResponseCache for answers using a vector search. If the confidence score is below a threshold (to be determined through testing later) the question will do the full LLM cycle.
* Once the answer facts have been established they need to then go through a further LLM phase (known as the ResponseBot LLM) which will aim to match the tone of the original question to provide an answer that isn't overly verbose or academic as the goal is for use in real world social media
* The ResponseBot LLM will later be extended to adjust what response can be achieved by the user, such as adding sarcasm or being more casual with language such as "LOL, ...."
* Guard rails will need to be included to prevent abuse of the chat bot including rate limits and checking the question is a climate related question and that it presents a sceptical view point
* Questions and Answers throughout the entire flow need to be stored for tracing issues in the future

![ClimateBotDesign.png](Project/ClimateBotDesign.png)
