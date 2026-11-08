"""Cognitrail keeps external tracing disabled in its own process by default."""
import os

os.environ['LANGSMITH_TRACING']='false'
os.environ['LANGCHAIN_TRACING_V2']='false'
