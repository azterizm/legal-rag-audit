FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Install the package
RUN pip install --no-cache-dir -e .

# Create volume for output reports
VOLUME ["/output"]

# Set entrypoint
ENTRYPOINT ["legal-rag-audit"]
