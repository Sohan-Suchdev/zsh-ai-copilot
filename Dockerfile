# Use the official, lightweight Python 3.12 image
FROM python:3.12-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file first (this caches dependencies to speed up future builds)
COPY requirements.txt .

# Install the required Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend code into the container
COPY backend/ backend/

# Expose the port FastAPI runs on
EXPOSE 8000

# Command to run the FastAPI server, bound to all network interfaces (0.0.0.0)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]