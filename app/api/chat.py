from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agent.agent import Agent
from app.database.session import get_session
from app.retriever.retriever import GoldRetriever
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])

agent = Agent()
retriever = GoldRetriever()


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest, session: Session = Depends(get_session)):
    ctx = retriever.retrieve(request.message, session)
    answer, sources = agent.answer(request.message, ctx)
    return ChatResponse(answer=answer, sources=sources)
