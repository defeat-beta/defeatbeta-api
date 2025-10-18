class OpenAIConfiguration:
    def __init__(
            self,
            model="Qwen/Qwen3-8B",
            temperature=0,
            top_p=0,
            top_k=5,
            tool_choice="auto"
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

    def get_top_k(self):
        return self.top_k

    def get_tool_choice(self):
        return self.tool_choice
