from app.ai.local import LocalAssistant
from app.ai.openai_compatible import OpenAICompatibleModel
from app.ai.openai_responses import OpenAIResponsesModel
from app.ai.provider import AssistantModel
from app.core.config import settings
from app.core.exceptions import AppError


def build_assistant_model() -> AssistantModel:
    if settings.ai_provider == "local":
        return LocalAssistant()
    if settings.ai_provider == "openai":
        model_class = (
            OpenAIResponsesModel
            if settings.ai_openai_api == "responses"
            else OpenAICompatibleModel
            if settings.ai_openai_api == "chat"
            else None
        )
        if model_class is None:
            raise AppError(
                "AI_OPENAI_API must be responses or chat",
                status_code=400,
            )
        return model_class(
            api_key=settings.ai_api_key,
            model=settings.ai_model,
            base_url=settings.ai_base_url,
            timeout=settings.ai_timeout_seconds,
        )
    raise AppError(
        f"Unknown AI_PROVIDER {settings.ai_provider}",
        status_code=400,
    )
