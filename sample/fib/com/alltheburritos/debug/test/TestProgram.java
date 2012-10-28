package com.alltheburritos.debug.test;

public class TestProgram {

  private Nest n;

  public TestProgram() {
    n = new Nest();
  }

  public void run() throws Exception {
    Nest nest = new Nest();
    while (true) {
      System.out.println("fib(" + n.get() + ") = " + fib(n.get()));
      Thread.sleep(1000);
      n.inc();
    }
  }

  public class Nest {
    private static final String egg = "0";

    private int n;

    public Nest() {
      this.n = 0;
    }

    public int get() {
      return n;
    }

    public void inc() {
      n++;
      if (n > 20) n = 0;
    }
  }

  public int asdf = 1;
  public String omg = "wtf";

  public static void main(String[] args) throws Exception {
    new TestProgram().run();
  }

  private static int fib(int n) {
    if (n <= 0) return 1;
    if (n == 1) return 1;
    return fib(n-1) + fib(n-2);
  }
}
