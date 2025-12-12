
import os
import sys

# Add the current directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from API_Server import app
import config

if __name__ == "__main__":
    print("----------------------------------------------------------------")
    print("Starting Claroz Agent Local Server...")
    print("----------------------------------------------------------------")
    
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=True, host='0.0.0.0', port=port)
