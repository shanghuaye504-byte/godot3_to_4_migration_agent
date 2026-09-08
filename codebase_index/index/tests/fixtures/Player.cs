using Godot;

public partial class Player : CharacterBody2D
{
    public int Hp = 100;

    public void TakeDamage(int amount)
    {
        Hp -= amount;
        if (Hp <= 0)
        {
            Die();
        }
    }

    private void Die()
    {
        QueueFree();
    }
}
