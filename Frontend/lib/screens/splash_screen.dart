import 'dart:async';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/user_model.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  _SplashScreenState createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  @override
  void initState() {
    super.initState();
    _checkLoginStatus();
  }

  Future<void> _checkLoginStatus() async {
    final prefs = await SharedPreferences.getInstance();
    // Check if the user is logged in
    final bool isLoggedIn = prefs.getBool('isLoggedIn') ?? false;

    // Wait for a couple of seconds for the splash screen
    await Future.delayed(const Duration(seconds: 3));
    
    if (!mounted) return; // Check if the widget is still in the tree

    if (isLoggedIn) {
      // If logged in, get user data and go to home
      final userName = prefs.getString('userName') ?? '';
      final userEmail = prefs.getString('userEmail') ?? '';
      final user = User(name: userName, email: userEmail);
      Navigator.of(context).pushReplacementNamed('/home', arguments: user);
    } else {
      // If not logged in, go to create account
      Navigator.of(context).pushReplacementNamed('/create_account');
    }
  }

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: Color(0xFF1a1a1a),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.analytics, size: 100, color: Colors.blue),
            SizedBox(height: 20),
            Text(
              'AI Analyst',
              style: TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.bold,
                color: Colors.white,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
