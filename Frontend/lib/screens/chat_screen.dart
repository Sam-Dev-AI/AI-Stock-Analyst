import 'package:flutter/material.dart';
import '../widgets/chat_bubble.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  _ChatScreenState createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final TextEditingController _controller = TextEditingController();
  // The message list now starts empty.
  final List<Map<String, dynamic>> _messages = [];

  void _sendMessage() {
    if (_controller.text.isEmpty) return;
    setState(() {
      _messages.add({"text": _controller.text, "isMe": true});
      // TODO: Add logic to get a response from the AI and add it to the list.
      // For example:
      // final aiResponse = getAiResponse(_controller.text);
      // _messages.add({"text": aiResponse, "isMe": false});
    });
    _controller.clear();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // The message list will be empty initially.
        Expanded(
          child: _messages.isEmpty
              ? const Center(
                  child: Text(
                    'Ask me anything to start...',
                    style: TextStyle(color: Colors.grey, fontSize: 16),
                  ),
                )
              : ListView.builder(
                  padding: const EdgeInsets.all(16.0),
                  itemCount: _messages.length,
                  itemBuilder: (context, index) {
                    final message = _messages[index];
                    return ChatBubble(
                      text: message['text'],
                      isMe: message['isMe'],
                    );
                  },
                ),
        ),
        // Suggestion chips (optional, can be removed if not needed for blank screen)
        Container(
          padding: const EdgeInsets.symmetric(vertical: 8.0, horizontal: 12.0),
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: [
                _buildSuggestionChip("What are the top-performing stocks?"),
                const SizedBox(width: 8),
                _buildSuggestionChip("Latest news on Nifty 50"),
              ],
            ),
          ),
        ),
        // Text input field
        Padding(
          padding: const EdgeInsets.all(12.0),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _controller,
                  style: const TextStyle(color: Colors.white),
                  decoration: InputDecoration(
                    prefixIcon: const Icon(Icons.mic, color: Colors.grey),
                    hintText: 'Ask me anything...',
                    hintStyle: const TextStyle(color: Colors.grey),
                    filled: true,
                    fillColor: const Color(0xFF2a2a2a),
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(30.0), borderSide: BorderSide.none),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              IconButton(
                icon: const Icon(Icons.send, color: Colors.white),
                style: IconButton.styleFrom(backgroundColor: Colors.blue, padding: const EdgeInsets.all(14)),
                onPressed: _sendMessage,
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildSuggestionChip(String text) {
    return ActionChip(
      label: Text(text, style: const TextStyle(color: Colors.white)),
      onPressed: () { _controller.text = text; },
      backgroundColor: const Color(0xFF2a2a2a),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20), side: const BorderSide(color: Colors.blue)),
    );
  }
}
