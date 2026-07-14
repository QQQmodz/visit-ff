"""
Vercel Serverless Entry Point
"""
from .routes import app

def handler(request, context):
    """Vercel serverless handler"""
    return app(request, context)

# For local development
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
