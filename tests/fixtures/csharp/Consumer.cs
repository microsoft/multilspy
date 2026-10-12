namespace Example
{
    public static class Consumer
    {
        public static int Read() => Constants.Answer;
        public static int ReadAgain() => Constants.Answer;
        public static Choice Pick() => Choice.First;
    }
}
