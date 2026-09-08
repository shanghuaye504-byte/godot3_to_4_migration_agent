#include "native.hpp"

class PlayerNative : public CharacterBody2D {
public:
    void take_damage(int amount) {
        hp -= amount;
        if (hp <= 0) {
            die();
        }
    }

private:
    int hp = 100;
    void die();
};

void PlayerNative::die() {
    queue_free();
}
