import 'package:flutter/material.dart';
import '../models/user_model.dart';
import 'chat_screen.dart';
import 'profile_screen.dart';

class HomeScreen extends StatefulWidget {
  final User user;
  const HomeScreen({super.key, required this.user});

  @override
  _HomeScreenState createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _selectedIndex = 0;
  late final List<Widget> _widgetOptions;

  static const List<String> _titles = <String>[
    'AI Analyst',
    'Portfolio',
    'Insights',
    'Profile',
  ];

  @override
  void initState() {
    super.initState();
    _widgetOptions = <Widget>[
      const ChatScreen(),
      const Center(
        child: Text('Portfolio Screen', style: TextStyle(color: Colors.white)),
      ),
      const Center(
        child: Text('Insights Screen', style: TextStyle(color: Colors.white)),
      ),
      ProfileScreen(user: widget.user), // Pass user to ProfileScreen
    ];
  }

  void _onItemTapped(int index) {
    setState(() {
      _selectedIndex = index;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: _selectedIndex == 0
            ? const Icon(Icons.arrow_back, color: Colors.white)
            : null,
        automaticallyImplyLeading: false,
        title: Text(
          _titles.elementAt(_selectedIndex),
          style: const TextStyle(color: Colors.white),
        ),
        backgroundColor: const Color(0xFF1a1a1a),
        elevation: 0,
      ),
      body: IndexedStack(index: _selectedIndex, children: _widgetOptions),
      bottomNavigationBar: BottomNavigationBar(
        items: const <BottomNavigationBarItem>[
          BottomNavigationBarItem(icon: Icon(Icons.chat_bubble), label: 'Chat'),
          BottomNavigationBarItem(icon: Icon(Icons.work), label: 'Portfolio'),
          BottomNavigationBarItem(
            icon: Icon(Icons.insights),
            label: 'Insights',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.person),
            label: 'Profile',
          ), // Changed to Profile
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
