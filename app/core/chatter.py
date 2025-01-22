from abc import ABC, abstractmethod

class Chatter(ABC):
    @abstractmethod
    def chat(self, message: str) -> str:
        pass
