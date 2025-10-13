import 'package:flutter/material.dart';
import 'models/user_model.dart';
import 'screens/splash_screen.dart';
import 'screens/create_account_screen.dart';
import 'screens/login_screen.dart';
import 'screens/home_screen.dart';

void main() {
  runApp(const AIAnalystApp());
}

class AIAnalystApp extends StatelessWidget {
  const AIAnalystApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AI Analyst',
      theme: ThemeData(
        brightness: Brightness.dark,
        primaryColor: const Color(0xFF1a1a1a),
        scaffoldBackgroundColor: const Color(0xFF1a1a1a),
        primarySwatch: Colors.blue,
        visualDensity: VisualDensity.adaptivePlatformDensity,
      ),
      debugShowCheckedModeBanner: false,
      initialRoute: '/',
      routes: {
        '/': (context) => const SplashScreen(),
        '/create_account': (context) => const CreateAccountScreen(),
        '/login': (context) => const LoginScreen(),
      },
      // Special handling for routes that need arguments
      onGenerateRoute: (settings) {
        if (settings.name == '/home') {
          final args = settings.arguments as User;
          return MaterialPageRoute(
            builder: (context) {
              return HomeScreen(user: args);
            },
          );
        }
        // Handle other routes if needed
        return null;
      },
    );
  }
}