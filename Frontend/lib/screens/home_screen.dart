import 'package:flutter/material.dart';
import 'chat_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  _HomeScreenState createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _selectedIndex = 0;

  static final List<String> _titles = <String>[
    'AI Analyst',
    'Portfolio',
    'Insights',
    'Settings',
  ];

  static final List<Widget> _widgetOptions = <Widget>[
    const ChatScreen(),
    const Center(child: Text('Portfolio Screen', style: TextStyle(color: Colors.white))),
    const Center(child: Text('Insights Screen', style: TextStyle(color: Colors.white))),
    const Center(child: Text('Settings Screen', style: TextStyle(color: Colors.white))),
  ];

  void _onItemTapped(int index) {
    setState(() {
      _selectedIndex = index;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: _selectedIndex == 0 ? const Icon(Icons.arrow_back, color: Colors.white) : null,
        automaticallyImplyLeading: false,
        title: Text(_titles.elementAt(_selectedIndex), style: const TextStyle(color: Colors.white)),
        backgroundColor: const Color(0xFF1a1a1a),
        elevation: 0,
      ),
      body: IndexedStack(
        index: _selectedIndex,
        children: _widgetOptions,
      ),
      bottomNavigationBar: BottomNavigationBar(
        items: const <BottomNavigationBarItem>[
          BottomNavigationBarItem(icon: Icon(Icons.chat_bubble), label: 'Chat'),
          BottomNavigationBarItem(icon: Icon(Icons.work), label: 'Portfolio'),
          BottomNavigationBarItem(icon: Icon(Icons.insights), label: 'Insights'),
          BottomNavigationBarItem(icon: Icon(Icons.settings), label: 'Settings'),
        ],
        currentIndex: _selectedIndex,
        selectedItemColor: Colors.blue,
        unselectedItemColor: Colors.grey,
        backgroundColor: const Color(0xFF2a2a2a),
        type: BottomNavigationBarType.fixed,
        onTap: _onItemTapped,
      ),
    );
  }
}
