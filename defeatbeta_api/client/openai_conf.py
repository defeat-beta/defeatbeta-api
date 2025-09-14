class OpenAIConfiguration:
    def __init__(
            self,
            model="Qwen/Qwen3-8B",
            temperature=0,
            top_p=0.95,
            stream=False
    ):
        configs = locals()
        configs.pop('self')

        for key, value in configs.items():
            setattr(self, key, value)

    def get_model(self):
        return self.model

    def get_temperature(self):
        return self.temperature

    def get_top_p(self):
        return self.top_p

    def get_stream(self):
        return self.stream
